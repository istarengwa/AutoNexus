import React, { useState } from 'react';
import { Send } from 'lucide-react';
import { api } from '../services/api';

export default function AgentBuilder() {
  const [chatHistory, setChatHistory] = useState([{ role: 'agent', content: "Describe your automation need (e.g., 'Analyze Discord chat and create Atoms').", type: 'text' }]);
  const [userInput, setUserInput] = useState('');
  const [formData, setFormData] = useState({});
  const [formMeta, setFormMeta] = useState({ source: '', dest: '' });

  const sendMessage = async () => {
    if (!userInput.trim()) return;
    const newHist = [...chatHistory, { role: 'user', content: userInput, type: 'text' }];
    setChatHistory(newHist);
    setUserInput('');

    try {
      const data = await api.chatWithAgent(userInput);
      setChatHistory(prev => [...prev, data]);
      
      if (data.type === 'form') {
        setFormMeta({ source: data.formData.serviceSource, dest: data.formData.serviceDest });
        setFormData({});
      }
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'agent', content: "Backend Error.", type: 'error' }]);
    }
  };

  const deploy = async () => {
    try {
      const payload = { serviceSource: formMeta.source, serviceDest: formMeta.dest, settings: formData };
      const data = await api.createAgent(payload);
      setChatHistory(prev => [...prev, { role: 'agent', content: data.message, type: 'success' }]);
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'agent', content: "Deployment failed.", type: 'error' }]);
    }
  };

  return (
    <div className="h-[600px] flex flex-col bg-slate-900 rounded-xl border border-slate-700">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, i) => (
          <div key={i} className={`p-4 rounded-xl max-w-[80%] ${msg.role === 'user' ? 'ml-auto bg-blue-600' : 'bg-slate-800 border border-slate-700'}`}>
            <div className="whitespace-pre-wrap">{msg.content}</div>
            {msg.type === 'form' && (
              <div className="mt-4 space-y-3 bg-slate-900/50 p-3 rounded-lg border border-slate-700/50">
                {msg.formData.fields.map((f, idx) => (
                  <div key={idx}>
                    <label className="text-xs text-slate-400 block mb-1">{f.label}</label>
                    {f.type === 'textarea' ? (
                       <textarea 
                         placeholder={f.placeholder}
                         className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white outline-none focus:border-blue-500 h-20 font-mono"
                         onChange={e => { setFormData(prev => ({ ...prev, [f.key]: e.target.value })); }}
                       />
                    ) : (
                       <input 
                         type={f.type} 
                         placeholder={f.placeholder}
                         className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white outline-none focus:border-blue-500"
                         onChange={e => { setFormData(prev => ({ ...prev, [f.key]: e.target.value })); }}
                       />
                    )}
                  </div>
                ))}
                <button onClick={deploy} className="w-full bg-emerald-600 hover:bg-emerald-500 py-2 rounded text-sm font-bold mt-2 transition-colors">Activate Agent</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="p-4 border-t border-slate-700 flex gap-2">
        <input value={userInput} onChange={e => setUserInput(e.target.value)} className="flex-1 bg-slate-800 rounded-lg px-4 outline-none text-white" onKeyDown={e => e.key === 'Enter' && sendMessage()} placeholder="Type your request..." />
        <button onClick={sendMessage} className="bg-blue-600 p-2 rounded-lg text-white"><Send className="w-5 h-5" /></button>
      </div>
    </div>
  );
}