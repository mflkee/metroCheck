import { apiRequest } from "@/api/client";

export type Protocol = {
  id: string;
  file_name: string;
  status: string;
  extracted_at: string | null;
};

export type ProtocolListResponse = {
  items: Protocol[];
  total: number;
};

export async function scanProtocols(): Promise<{ task_id: string }> {
  return apiRequest<{ task_id: string }>("/protocols/scan", {
    method: "POST",
  });
}

export async function listProtocols(): Promise<ProtocolListResponse> {
  return apiRequest<ProtocolListResponse>("/protocols/list");
}

export async function extractProtocol(protocolId: string): Promise<Protocol> {
  return apiRequest<Protocol>(`/protocols/${protocolId}/extract`, {
    method: "POST",
  });
}
