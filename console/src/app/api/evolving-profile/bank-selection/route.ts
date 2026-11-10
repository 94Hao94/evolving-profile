import { resolveBankSelection } from "@/lib/bank-selection.server";

export const dynamic="force-dynamic";
export async function GET(request:Request) {
  const requested=new URL(request.url).searchParams.get("bankId");
  const result=await resolveBankSelection(requested||null);
  return Response.json(result,{
    status:result.status==="missing" ? 404 : result.status==="unavailable" ? 503 : 200,
    headers:{"Cache-Control":"no-store"},
  });
}
