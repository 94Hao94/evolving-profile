export type BankAvailability = "ready" | "missing" | "unavailable";
export interface BankSelection {
  schema: "ep.bank-selection.v1";
  requested_bank_id: string | null;
  selected_bank_id: string | null;
  status: BankAvailability | "unconfigured";
  primary: {bank_id:string|null; status:BankAvailability|"unconfigured"};
}
