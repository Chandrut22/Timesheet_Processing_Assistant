import { http } from "@/lib/axios";
import { SubmissionReadSchema } from "@/features/submissions";
import { checked } from "@/services/response";

export const uploadService = {
  upload: (files: File[], companyId?: string, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (companyId) form.append("company_id", companyId);
    return checked(
      SubmissionReadSchema,
      http.post("/api/uploads", form, {
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      }),
    );
  },
};
