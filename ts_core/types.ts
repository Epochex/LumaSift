export type QwenStatus = "done" | "cache-hit" | "failed" | "running" | "queued" | "not_reviewed" | string;

export interface EditorialVerdict {
  action?: "keep" | "maybe" | "reject" | string;
  confidence?: number;
  one_line_reason?: string;
}

export interface CropBox {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  reason?: string;
  composition_goal?: string;
}

export interface EditingPlan {
  edit_intent?: string;
  crop_plan?: {
    aspect_ratio?: string;
    keep?: string[];
    remove_or_reduce?: string[];
    crop_box?: CropBox;
    reason?: string;
  };
  local_masks?: Array<{
    target?: string;
    operation?: string;
    reason?: string;
    settings?: Record<string, string | number>;
  }>;
}

export interface PhotoReviewRecord {
  filename?: string;
  category?: string;
  analysis_source?: string;
  analysis_quality?: string;
  qwen_status?: QwenStatus;
  qwen_prompt_version?: string;
  editorial_verdict?: EditorialVerdict;
  professional_review?: Record<string, string>;
  visible_inventory?: {
    main_subject?: string;
    people?: Array<{
      id?: string;
      region?: string;
      visibility?: string;
      pose_or_motion?: string;
      motion?: string;
      confidence?: number;
    }>;
    setting_context?: string[];
    gesture_expression_motion?: string[];
  };
  visible_evidence?: string[];
  critical_flaws?: string[];
  hallucination_checks?: {
    unsupported_claims?: string[];
    uncertain_objects?: string[];
    spatial_sanity_check?: string;
  };
  storytelling_score?: number;
  human_documentary_value_score?: number;
  decisive_moment_score?: number;
  moment_status?: string;
  frame_failure_reasons?: string[];
  why_deprioritize?: string[];
  selection_risk?: string;
  edit_vs_select_warning?: string;
  subject_identity_uncertainty?: string;
  subject_relationship?: string;
  decisive_moment_read?: string;
  story_interpretation?: string;
  recommended_style?: string;
  specific_edit_parameters?: Record<string, string | number>;
  editing_plan?: EditingPlan;
}

export interface EditingAdvice {
  filename: string;
  editing_advice_source: "vision_evidence" | "rejected_by_vision" | "technical_draft";
  blocked_reason: string;
  editing_intent: string;
  lightroom_parameters: Record<string, string>;
  crop_plan: {
    aspect_ratio: string;
    keep: string[];
    remove_or_reduce: string[];
    reason: string;
  };
  local_masks: EditingPlan["local_masks"];
}
