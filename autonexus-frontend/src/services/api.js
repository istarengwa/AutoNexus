const API_URL = "http://localhost:8000/api";

// Helper générique pour gérer les erreurs
const request = async (endpoint, options = {}) => {
  try {
    const res = await fetch(`${API_URL}${endpoint}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    return await res.json();
  } catch (e) {
    console.error(`API Error on ${endpoint}:`, e);
    throw e;
  }
};

export const api = {
  // System
  checkHealth: () => fetch(`${API_URL}/system/stats`).then(r => r.ok),
  getStats: () => request('/system/stats'),

  // Credentials
  checkCredential: (serviceId) => request(`/credentials/check/${serviceId}`),
  saveCredential: (serviceId, apiKey) => request('/credentials', {
    method: 'POST',
    body: JSON.stringify({ serviceId, apiKey })
  }),

  // Workflows (Agents)
  getWorkflows: () => request('/workflows'),
  createAgent: (payload) => request('/agent/deploy', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  chatWithAgent: (message) => request('/agent/chat', {
    method: 'POST',
    body: JSON.stringify({ message, history: [] })
  }),
  toggleAgentStatus: (id, status) => request(`/agent/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status })
  }),
  updateAgentSettings: (id, settings) => request(`/agent/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ settings })
  }),
  deleteAgent: (id) => request(`/agent/${id}`, {
    method: 'DELETE'
  })
};