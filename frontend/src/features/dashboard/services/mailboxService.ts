import { http } from "@/lib/axios";
import { checked } from "@/services/response";
import { MailboxCheckSchema, MailboxStatusSchema } from "../types/mailbox";

export const mailboxService = {
  getStatus: () => checked(MailboxStatusSchema, http.get("/api/email/status")),
  checkNow: () => checked(MailboxCheckSchema, http.post("/api/email/check-now")),
  getCheck: (requestId: string) =>
    checked(MailboxCheckSchema, http.get(`/api/email/check-now/${requestId}`)),
};
