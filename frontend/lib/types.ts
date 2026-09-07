export type ContactStatus =
  | "new"
  | "enriched"
  | "contacted"
  | "replied"
  | "not_interested"
  | "meeting_booked";

export type Gender = "m" | "f" | "d";

export interface Organisation {
  id: number;
  name: string;
  domain: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface DraftSummary {
  id: number;
  subject: string;
  generated_at: string;
}

export interface Contact {
  id: number;
  organisation_id: number;
  first_name: string;
  last_name: string;
  gender: Gender | null;
  email: string | null;
  position: string | null;
  status: ContactStatus;
  notes: string;
  last_enriched_at: string | null;
  last_enrichment_error: string | null;
  last_generated_at: string | null;
  last_generation_error: string | null;
  latest_draft: DraftSummary | null;
  created_at: string;
  updated_at: string;
}

export interface Draft {
  id: number;
  contact_id: number;
  template_id: number;
  prompt_id: number;
  subject: string;
  body: string;
  generated_at: string;
  created_at: string;
  updated_at: string;
}

export interface Template {
  id: number;
  name: string;
  subject_hint: string | null;
  body: string;
  is_archived: boolean;
  missing_placeholders: string[];
  created_at: string;
  updated_at: string;
}

export interface Prompt {
  id: number;
  text: string;
  is_active: boolean;
  missing_placeholders: string[];
  created_at: string;
  updated_at: string;
}

export type TodoType = "send" | "follow_up" | "manual";
export type TodoStatus = "scheduled" | "open" | "done" | "cancelled";

export interface Todo {
  id: number;
  type: TodoType;
  title: string;
  contact_id: number;
  draft_id: number | null;
  sent_message_id: number | null;
  due_at: string;
  status: TodoStatus;
  completed_at: string | null;
  completed_via: string | null;
  created_at: string;
  updated_at: string;
}

export interface SaveToMailboxResponse {
  todo: Todo;
  draft: {
    id: number;
    contact_id: number;
    subject: string;
    body: string;
    template_id: number;
    generated_at: string;
    mailbox_folder: string | null;
    mailbox_uid: number | null;
    mailbox_stored_at: string | null;
    created_at: string;
    updated_at: string;
  };
  mailbox: { folder: string; uid: number | null; stored_at: string };
  replaced_previous: boolean;
}

export interface SentMessage {
  id: number;
  contact_id: number;
  subject: string;
  body: string;
  sent_at: string;
  delivery_status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface SettingsView {
  hunter_api_key_set: boolean;
  openai_api_key_set: boolean;
  smtp: {
    host: string | null;
    port: number | null;
    username_set: boolean;
    password_set: boolean;
  };
  imap: {
    host: string | null;
    port: number | null;
    username_set: boolean;
    password_set: boolean;
    use_tls: boolean;
    drafts_folder: string | null;
    drafts_folder_detected: string | null;
  };
  sender_display_name: string | null;
  sender_email: string | null;
  follow_up_cadence_days: number;
  default_template_id: number | null;
  openai_model: string;
  timezone: string;
  master_password_set: boolean;
}

export interface TestConnectionResult {
  ok: boolean;
  message: string;
}

export interface ImapTestConnectionResult extends TestConnectionResult {
  resolved_drafts_folder: string | null;
}

export interface DashboardActivity {
  window_days: number;
  leads_added: number;
  drafts_generated: number;
  emails_sent: number;
  follow_ups_due: number;
  replies_logged: number;
  delta_vs_prior: {
    leads_added: number;
    drafts_generated: number;
    emails_sent: number;
    follow_ups_due: number;
    replies_logged: number;
  };
}

export interface DashboardOverview {
  onboarding_required: boolean;
  todos?: {
    overdue_count: number;
    due_today_count: number;
    next_action: { todo_id: number; title: string; due_at: string } | null;
  };
  activity?: DashboardActivity;
  activity_30d?: DashboardActivity;
  funnel_30d?: {
    sent: number;
    replied: number;
    meeting_booked: number;
    reply_rate: number;
    booking_rate: number;
  };
}
