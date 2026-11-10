import { describe, it, expect, vi, afterEach } from "vitest";
import { resolveBankSelection } from "@/lib/bank-selection.server";
import { bankIdFromPathname } from "@/lib/bank-path";

const profile = async () => JSON.stringify({bankId:"primary/project", apiKey:"must-not-escape"});
const existing = async (id:string) => id === "missing" ? "missing" as const : "ready" as const;

describe("bank selection authority", () => {
  afterEach(()=>vi.unstubAllGlobals());
  it("resolves the configured primary rather than a hardcoded or first-listed bank", async () => {
    expect(await resolveBankSelection(null, profile, existing)).toEqual({
      schema:"ep.bank-selection.v1", requested_bank_id:null, selected_bank_id:"primary/project",
      status:"ready", primary:{bank_id:"primary/project",status:"ready"},
    });
  });
  it("preserves an explicitly selected valid other bank", async () => {
    const result=await resolveBankSelection("other", profile, existing);
    expect(result.selected_bank_id).toBe("other");
    expect(result.primary.bank_id).toBe("primary/project");
  });
  it("does not substitute primary or an empty bank for an invalid explicit address", async () => {
    const result=await resolveBankSelection("missing",profile,existing);
    expect(result.status).toBe("missing"); expect(result.selected_bank_id).toBeNull();
    expect(result.primary.status).toBe("ready");
  });
  it("does not infer a primary when installation has no profile", async () => {
    const result=await resolveBankSelection(null, async()=>{throw Object.assign(new Error("missing"),{code:"ENOENT"});},existing);
    expect(result.status).toBe("unconfigured"); expect(result.selected_bank_id).toBeNull();
  });
  it("keeps corrupt config unknown, not unconfigured or ready",async()=>{
    const result=await resolveBankSelection(null,async()=>"{bad",existing);
    expect(result.status).toBe("unavailable"); expect(result.primary.bank_id).toBeNull();
  });
  it("keeps explicit valid banks usable if primary config is unavailable",async()=>{
    const result=await resolveBankSelection("other",async()=>"{bad",existing);
    expect(result.status).toBe("ready"); expect(result.selected_bank_id).toBe("other");
    expect(result.primary.status).toBe("unavailable");
  });
  it("does not turn an authentication or network failure into bank absence",async()=>{
    const result=await resolveBankSelection("other",profile,async()=>"unavailable");
    expect(result.status).toBe("unavailable"); expect(result.selected_bank_id).toBeNull();
  });
  it("checks the primary only once when it is the explicit selection",async()=>{
    const calls:string[]=[];
    await resolveBankSelection("primary/project",profile,async id=>{calls.push(id);return "ready";});
    expect(calls).toEqual(["primary/project"]);
  });
  it("does not expose provider credentials from the profile",async()=>{
    expect(JSON.stringify(await resolveBankSelection(null,profile,existing))).not.toContain("must-not-escape");
  });
  it.each([401,403,500,503])("treats upstream HTTP %s as unavailable, never missing",async status=>{
    vi.stubGlobal("fetch",async()=>new Response("{}",{status}));
    const result=await resolveBankSelection(null,profile);
    expect(result.status).toBe("unavailable");
  });
  it("validates an encoded bank through a read-only profile request",async()=>{
    const calls:Array<{url:string;method:unknown}>=[];
    vi.stubGlobal("fetch",async(url:string,init:RequestInit)=>{
      calls.push({url,method:init.method??"GET"});
      return Response.json({bank_id:"primary/project",name:"Empty but valid"});
    });
    expect((await resolveBankSelection(null,profile)).selected_bank_id).toBe("primary/project");
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toMatch(/\/banks\/primary%2Fproject\/profile$/);
    expect(calls[0].method).toBe("GET");
  });
  it("requires a matching bank identity in a successful profile response",async()=>{
    vi.stubGlobal("fetch",async()=>Response.json({bank_id:"wrong"}));
    expect((await resolveBankSelection(null,profile)).status).toBe("unavailable");
  });
  it("uses actual 404 profile evidence, not a missing entry in a paginated list",async()=>{
    vi.stubGlobal("fetch",async()=>Response.json({detail:"Bank 'primary/project' not found"},{status:404}));
    expect((await resolveBankSelection(null,profile)).status).toBe("missing");
  });
  it.each(["Not Found", JSON.stringify({detail:"Not Found"}), JSON.stringify({detail:"Bank 'another' not found"})])(
    "does not mistake a route or proxy 404 for evidence about the requested bank: %s",async body=>{
      vi.stubGlobal("fetch",async()=>new Response(body,{status:404}));
      expect((await resolveBankSelection(null,profile)).status).toBe("unavailable");
    });
});

describe("bank URL parsing",()=>{
  it("malformed escaping cannot crash the bank provider",()=>{
    expect(bankIdFromPathname("/en/banks/%XX")).toBeNull();
  });
  it("decodes encoded slash and percent IDs once",()=>{
    expect(bankIdFromPathname("/zh-CN/banks/team%2Fproject%252F")).toBe("team/project%2F");
  });
});
