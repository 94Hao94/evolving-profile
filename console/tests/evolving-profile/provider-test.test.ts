import { describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/evolving-profile/provider-test/route";

function request(payload: Record<string, unknown>) {
  return new Request("http://localhost/api/evolving-profile/provider-test", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

describe("Provider 连接测试", () => {
  it("不会把页面掩码写入 Authorization，并返回中文成功状态", async () => {
    let authorization = "";
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      authorization = new Headers(init?.headers).get("authorization") ?? "";
      return new Response(JSON.stringify({ data: [] }), { status: 200 });
    }));

    const response = await POST(request({ base_url: "http://provider.test/v1", model: "demo", api_key: "••••bggK" }));
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body).toMatchObject({ ok: true, detail: "Provider 连接正常" });
    expect(authorization).toMatch(/^Bearer /);
    expect(authorization).not.toContain("•");
  });

  it("拒绝非 ASCII 密钥并给出中文提示", async () => {
    const response = await POST(request({ base_url: "http://provider.test/v1", model: "demo", api_key: "密钥" }));
    const body = await response.json();
    expect(response.status).toBe(400);
    expect(body.error).toContain("API Key 含有非 ASCII 字符");
  });

  it("不把 ByteString 等底层英文异常直接返回给页面", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Cannot convert argument to a ByteString because the character at index 7 has a value of 8226 which is greater than 255.");
    }));

    const response = await POST(request({ base_url: "http://provider.test/v1", model: "demo", api_key: "sk-test" }));
    const body = await response.json();
    expect(response.status).toBe(502);
    expect(body.error).toBe("连接测试失败：页面中的掩码密钥不能直接发送，请重新输入真实 API Key。");
    expect(body.error).not.toContain("ByteString");
  });
});
