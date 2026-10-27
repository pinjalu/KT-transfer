export type Target = { provider: string; model: string }
export type Limits = { rpm: number; rpd: number; tpm: number; tpd: number }
export type Routing = {
  mode: 'automatic' | 'manual'; local_enabled: boolean; local_model: string; manual: Target;
  manual_fallback: boolean; overview_concurrency: number; project_limits: Limits;
  overview_interval_seconds?: number;
  providers: Record<string, { enabled: boolean; limits: Limits; timeout_seconds: number }>;
  routes: Record<string, Target[]>;
}
export type Generation = { provider?: string | null; model?: string | null; function?: string;
  latency_seconds?: number; input_tokens?: number | null; output_tokens?: number | null; usage_source?: string;
  attempts?: { provider: string; model: string; status: string; error?: string; latency_seconds?: number }[] }
export type AISettings = {
  monitoring?: { file: string; max_bytes: number; backups: number };
  config: Routing; features: Record<string,string>; catalog: (Target & {label: string; pricing: string})[];
  catalog_reviewed: string; catalog_expires: string; catalog_current: boolean; secure_storage: boolean;
  repo: string; permission: {providers: string[]; classification: string; source_types?: string[]}; policy: string;
  providers: Record<string,{key_configured: boolean; free_account_confirmed: boolean}>;
  usage: { usage_note: string; quota_scope: string; cooldowns: {provider:string;until_time:number;reason:string}[];
    shared_local_estimates?: {provider:string;window_seconds:number;requests:number;tokens:number;request_cap:number;token_cap:number;warning:boolean}[];
    last_24_hours: {provider:string;model:string;feature:string;requests:number;successes:number;average_seconds:number;
      input_tokens:number;output_tokens:number;usage_reported_requests:number;estimated_unreported_tokens:number}[];
    recent: {id:string;provider:string;model:string;feature:string;status:string;error:string;elapsed:number;reported:Record<string,number>}[] }
}
export type ConnectionTest = { ok: boolean; provider: string; model: string; code?: string; generation?: Generation; synthetic_only: boolean }
