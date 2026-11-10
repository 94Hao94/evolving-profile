"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { usePathname } from "next/navigation";
import { client } from "./api";
import { bankIdFromPathname } from "./bank-path";
import type { BankSelection } from "./bank-selection";
import { withBasePath } from "./base-path";

export interface BankInfo {
  bank_id: string;
  name: string | null;
  mission: string | null;
  created_at: string | null;
  updated_at: string | null;
  fact_count: number;
  last_document_at: string | null;
}

interface BankContextType {
  currentBank: string | null;
  setCurrentBank: (bank: string | null) => void;
  banks: string[];
  bankInfos: BankInfo[];
  banksLoading: boolean;
  loadBanks: () => Promise<void>;
  requestedBank: string | null;
  primaryBank: string | null;
  primaryReady: boolean;
  selectionStatus: BankSelection["status"] | "loading";
  refreshSelection: () => void;
}

const BankContext = createContext<BankContextType | undefined>(undefined);

export function BankProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const requestedBank = bankIdFromPathname(pathname);
  const invalidBankPath = /(?:^|\/)banks(?:\/|$)/.test(pathname??"") && !requestedBank;
  const [selection, setSelection] = useState<BankSelection | null>(null);
  const [selectionRevision, setSelectionRevision] = useState(0);
  // A previous bank's successful validation is never valid for the new URL.
  const activeSelection = selection?.requested_bank_id === requestedBank ? selection : null;
  const currentBank = !invalidBankPath && activeSelection?.status === "ready" ? activeSelection.selected_bank_id : null;
  const refreshSelection = useCallback(() => {
    setSelection(null);
    setSelectionRevision(value=>value+1);
  },[]);
  // Existing callers navigate immediately after selecting/creating/deleting.
  // Do not expose an unchecked choice to bank-scoped readers or writers.
  const setCurrentBank = useCallback((_bank:string|null)=>refreshSelection(),[refreshSelection]);
  const [bankInfos, setBankInfos] = useState<BankInfo[]>([]);
  const [banksLoading, setBanksLoading] = useState(true);

  const loadBanks = useCallback(async () => {
    setBanksLoading(true);
    try {
      const response = await client.listBanks();
      const infos: BankInfo[] =
        response.banks?.map((bank: any) => ({
          bank_id: bank.bank_id,
          name: bank.name ?? null,
          mission: bank.mission ?? null,
          created_at: bank.created_at ?? null,
          updated_at: bank.updated_at ?? null,
          fact_count: bank.fact_count ?? 0,
          last_document_at: bank.last_document_at ?? null,
        })) || [];
      setBankInfos(infos);
    } catch (error) {
      console.error("Error loading banks:", error);
    } finally {
      setBanksLoading(false);
    }
  },[]);

  // Derive bank IDs for backwards compatibility
  const banks = bankInfos.map((b) => b.bank_id);

  // Validate explicit routes; only routes without a Bank may default to primary.
  useEffect(() => {
    const abort=new AbortController();
    setSelection(null);
    const url=withBasePath("/api/evolving-profile/bank-selection")+
      (requestedBank ? `?bankId=${encodeURIComponent(requestedBank)}` : "");
    void fetch(url,{cache:"no-store",signal:abort.signal}).then(async response=>{
      const data=await response.json();
      if(data?.schema!=="ep.bank-selection.v1" || data.requested_bank_id!==requestedBank ||
        !["ready","missing","unavailable","unconfigured"].includes(data.status) ||
        !data.primary || (data.status==="ready" && typeof data.selected_bank_id!=="string")) {
        throw new Error("invalid_bank_selection_response");
      }
      if(!abort.signal.aborted) setSelection(data);
    }).catch(()=>{
      if(!abort.signal.aborted) setSelection({schema:"ep.bank-selection.v1",requested_bank_id:requestedBank,
        selected_bank_id:null,status:"unavailable",primary:{bank_id:null,status:"unavailable"}});
    });
    return ()=>abort.abort();
  }, [requestedBank,selectionRevision]);

  useEffect(() => {
    loadBanks();
  }, [loadBanks]);

  return (
    <BankContext.Provider
      value={{ currentBank, setCurrentBank, banks, bankInfos, banksLoading, loadBanks,
        requestedBank,primaryBank:activeSelection?.primary.bank_id??null,
        primaryReady:activeSelection?.primary.status==="ready",
        selectionStatus:invalidBankPath?"missing":activeSelection?.status??"loading",refreshSelection }}
    >
      {children}
    </BankContext.Provider>
  );
}

export function useBank() {
  const context = useContext(BankContext);
  if (context === undefined) {
    throw new Error("useBank must be used within a BankProvider");
  }
  return context;
}
