from copy import deepcopy
import json
from pka.llm.http import post_json, tokens
from pka.llm.types import ProviderError, Reply


def strict_schema(schema):
    """Require existing object properties for constrained output; validate locally too."""
    value = deepcopy(schema)
    def visit(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                node['additionalProperties'] = False
                node['required'] = list(node.get('properties', {}))
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
    visit(value)
    return value


def prepare(request):
    """Keep root unions inside an object; preserve every original constraint."""
    schema = strict_schema(request.schema)
    wrapped = 'anyOf' in schema
    messages = request.messages
    if wrapped:
        definitions = schema.pop('$defs',None)
        # Local JSON pointers must continue to address the original schema after
        # nesting it. This includes $defs and recursive root references.
        def relocate(node):
            if isinstance(node,dict):
                ref = node.get('$ref')
                if isinstance(ref,str) and (ref=='#' or ref.startswith('#/')) and not ref.startswith('#/$defs/'):
                    node['$ref'] = '#/properties/result' + ref[1:]
                for child in node.values(): relocate(child)
            elif isinstance(node,list):
                for child in node: relocate(child)
        relocate(schema)
        if definitions: relocate(definitions)
        # Groq's constrained decoder requires distinguishable union branches.
        # The application's answer/gap branches share their property names, so
        # give each an exclusive transport key instead of relaxing constraints.
        alternatives = schema.pop('anyOf')
        schema['anyOf'] = [
            {'type':'object','properties':{f'variant_{n+1}':branch},
             'required':[f'variant_{n+1}'],'additionalProperties':False}
            for n,branch in enumerate(alternatives)]
        schema = {'type':'object','properties':{'result':schema},'required':['result'],'additionalProperties':False}
        if definitions: schema['$defs']=definitions
        instruction = ('Transport format: result must contain exactly one variant_N property from the response schema. '
                       'Choose the matching variant and put the requested JSON answer inside it. '
                       'All answer and evidence rules still apply to that inner answer.')
        messages = deepcopy(messages)
        if messages and messages[0].get('role')=='system':
            messages[0]['content'] += '\n'+instruction
        else:
            messages.insert(0,{'role':'system','content':instruction})
    return messages, schema, wrapped


class Groq:
    def __init__(self, transport=None): self.transport = transport

    async def generate(self, request, target, key, timeout):
        messages, schema, wrapped = prepare(request)
        payload = {'model':target.model, 'messages':messages, 'temperature':request.temperature,
                   'max_completion_tokens':request.max_output_tokens, 'stream':False,
                   'response_format':{'type':'json_schema','json_schema':{
                       'name':'kt_response', 'strict':True, 'schema':schema}}}
        if target.model.startswith('openai/gpt-oss-'):
            payload['reasoning_effort'] = 'low'
        body, reported = await post_json('https://api.groq.com/openai/v1/chat/completions', payload,
            {'Authorization':'Bearer '+key}, timeout, self.transport)
        try:
            choice = body['choices'][0]
            if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                raise ProviderError('incomplete_response')
            content = choice['message']['content']
            if not isinstance(content, str): raise ProviderError('invalid_response')
            if wrapped:
                value = json.loads(content)
                if not isinstance(value,dict) or set(value)!={'result'} or not isinstance(value['result'],dict):
                    raise ProviderError('invalid_response')
                variants=value['result']
                allowed={f'variant_{n+1}' for n in range(len(request.schema['anyOf']))}
                if len(variants)!=1 or not set(variants)<=allowed:
                    raise ProviderError('invalid_response')
                answer=next(iter(variants.values()))
                if not isinstance(answer,dict): raise ProviderError('invalid_response')
                content = json.dumps(answer)
            usage = body.get('usage') or {}
            return Reply(content, tokens(usage.get('prompt_tokens')), tokens(usage.get('completion_tokens')), reported)
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise ProviderError('invalid_response') from None
