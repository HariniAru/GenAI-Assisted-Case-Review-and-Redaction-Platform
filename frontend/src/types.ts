export type CaseStatus = "OPEN" | "IN_PROGRESS" | "CLOSED";
export type RedactionSource = "AI" | "MANUAL";
export interface Case { id:number; case_number:string; status:CaseStatus; ai_summary:string|null; created_at:string; updated_at:string }
export interface RedactionType { id:number; name:string }
export interface UserSummary { id:number; first_name:string; last_name:string }
export interface Redaction { id:number; source:RedactionSource; redaction_text:string; starting_position:number; ending_position:number; created_at:string; updated_at:string; redaction_type:RedactionType; user:UserSummary }
export interface Activity { id:number; case_id:number; activity_uid:string; activity_type:string; description:string; created_at:string; redactions:Redaction[] }
export interface AIRecommendation { redaction_type:string; redaction_text:string; starting_position:number; reason:string }
