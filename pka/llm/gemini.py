from pka.llm.http import post_json, tokens
from pka.llm.types import ProviderError, Reply


class Gemini:
    def __init__(self, transport=None): self.transport = transport

    async def generate(self, request, target, key, timeout):
        system = '\n'.join(m['content'] for m in request.messages if m['role'] == 'system')
        contents = [{'role':'model' if m['role']=='assistant' else 'user', 'parts':[{'text':m['content']}]}
                    for m in request.messages if m['role'] != 'system']
        payload = {'systemInstruction':{'parts':[{'text':system}]}, 'contents':contents,
                   'generationConfig':{'temperature':request.temperature, 'maxOutputTokens':request.max_output_tokens,
                       'responseFormat':{'text':{'mimeType':'APPLICATION_JSON','schema':request.schema}}}}
        body, reported = await post_json(
            f'https://generativelanguage.googleapis.com/v1beta/models/{target.model}:generateContent', payload,
            {'x-goog-api-key':key}, timeout, self.transport)
        try:
            candidate = body['candidates'][0]
            if candidate.get('finishReason') != 'STOP': raise ProviderError('incomplete_response')
            content = ''.join(part['text'] for part in candidate['content']['parts']
                              if 'text' in part and not part.get('thought'))
            if not content: raise ProviderError('invalid_response')
            usage = body.get('usageMetadata') or {}
            output = tokens(usage.get('candidatesTokenCount'))
            thought = tokens(usage.get('thoughtsTokenCount')) or 0
            return Reply(content, tokens(usage.get('promptTokenCount')),
                         output + thought if output is not None else None, reported)
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError('invalid_response') from None
