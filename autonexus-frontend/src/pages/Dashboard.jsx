import React, { useState, useEffect } from 'react';
import { Bot, Edit2, Pause, Play, Trash2, Brain } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { api } from '../services/api';

export default function Dashboard({ isBackendOnline, setActiveTab }) {
  const [workflows, setWorkflows] = useState([]);
  const [editingWf, setEditingWf] = useState(null);
  // Ajout de custom_prompt dans le state du formulaire
  const [editForm, setEditForm] = useState({ bot_name: '', query: '', custom_prompt: '' });

  const fetchWorkflows = () => {
    if (isBackendOnline) {
      api.getWorkflows().then(data => setWorkflows(data)).catch(console.error);
    }
  };

  useEffect(() => { fetchWorkflows(); }, [isBackendOnline]);

  const toggleStatus = async (id, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'paused' : 'active';
    try {
      await api.toggleAgentStatus(id, newStatus);
      fetchWorkflows();
    } catch (e) { console.error(e); }
  };

  const deleteAgent = async (id) => {
    if (!confirm("Are you sure you want to delete this agent?")) return;
    try {
      await api.deleteAgent(id);
      fetchWorkflows();
    } catch (e) { console.error(e); }
  };

  const saveEdit = async () => {
    try {
      await api.updateAgentSettings(editingWf.id, editForm);
      setEditingWf(null);
      fetchWorkflows();
    } catch (e) { console.error(e); }
  };

  const openEdit = (wf) => {
    setEditingWf(wf);
    // Pré-remplissage du formulaire
    setEditForm({ 
      bot_name: wf.name, 
      query: wf.settings?.query || '',
      custom_prompt: wf.settings?.custom_prompt || '' 
    });
  };

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden relative">
      
      {/* Edit Modal */}
      {editingWf && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 p-6 rounded-xl w-full max-w-md shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <Edit2 className="w-5 h-5" /> Edit Agent
            </h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 uppercase font-bold">Bot Name</label>
                <input className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1" value={editForm.bot_name} onChange={e => setEditForm({...editForm, bot_name: e.target.value})} />
              </div>
              <div>
                <label className="text-xs text-slate-400 uppercase font-bold">Target / Query</label>
                <input className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1" value={editForm.query} onChange={e => setEditForm({...editForm, query: e.target.value})} />
              </div>
              
              {/* NEW: AI Prompt Field */}
              <div>
                <label className="text-xs text-purple-400 uppercase font-bold flex items-center gap-1">
                  <Brain className="w-3 h-3" /> AI Instructions (Pre-prompt)
                </label>
                <textarea 
                  className="w-full bg-slate-800 border border-purple-500/30 rounded p-2 text-white mt-1 text-xs font-mono h-24 focus:border-purple-500 outline-none" 
                  value={editForm.custom_prompt} 
                  onChange={e => setEditForm({...editForm, custom_prompt: e.target.value})}
                  placeholder="Ex: Summarize these messages into a single paragraph. Format as JSON Atom..."
                />
                <p className="text-[10px] text-slate-500 mt-1">Leave empty to send raw data directly.</p>
              </div>

              <div className="flex gap-2 pt-2">
                <button onClick={saveEdit} className="flex-1 bg-emerald-600 text-white py-2 rounded hover:bg-emerald-500 font-medium">Save Changes</button>
                <button onClick={() => setEditingWf(null)} className="flex-1 bg-slate-700 text-white py-2 rounded hover:bg-slate-600 font-medium">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="p-6 border-b border-slate-700 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Active Agents</h2>
        <button onClick={() => setActiveTab('builder')} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm flex items-center"><Bot className="w-4 h-4 mr-2" /> Create</button>
      </div>
      
      <div className="divide-y divide-slate-700">
        {workflows.map((wf) => (
          <div key={wf.id} className="p-6 flex items-center justify-between hover:bg-slate-750 transition-colors">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-1">
                <h3 className="font-medium text-white">{wf.name}</h3>
                <StatusBadge status={wf.status} />
                {wf.settings?.custom_prompt && (
                  <span className="text-[10px] bg-purple-900/30 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded flex items-center gap-1">
                    <Brain className="w-3 h-3" /> AI-Powered
                  </span>
                )}
              </div>
              <p className="text-slate-400 text-sm mb-2 flex items-center gap-2">
                <span className="capitalize">{wf.source}</span> 
                <span className="text-slate-600">→</span> 
                <span className="font-mono bg-slate-900 px-1 rounded">{wf.settings?.query}</span>
              </p>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <button onClick={() => openEdit(wf)} className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors" title="Edit Configuration">
                <Edit2 className="w-4 h-4" />
              </button>
              <button onClick={() => toggleStatus(wf.id, wf.status)} className={`p-2 rounded-lg transition-colors ${wf.status === 'active' ? 'text-emerald-400 hover:bg-emerald-900/20' : 'text-amber-400 hover:bg-amber-900/20'}`} title={wf.status === 'active' ? "Pause" : "Resume"}>
                {wf.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              </button>
              <button onClick={() => deleteAgent(wf.id)} className="p-2 hover:bg-red-900/30 rounded-lg text-slate-400 hover:text-red-400 transition-colors" title="Delete">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
        {workflows.length === 0 && <div className="p-8 text-center text-slate-500">No agents configured.</div>}
      </div>
    </div>
  );
}