import React, { useState } from "react";
import { Role, updateLmsRoleMappings } from "@/lib/admin/rolesApi";
import { X, Save, Loader2, Plus, Info } from "lucide-react";

interface LmsMappingModalProps {
  role: Role;
  currentMappings: string[];
  onClose: () => void;
  onSuccess: () => void;
}

export default function LmsMappingModal({ role, currentMappings, onClose, onSuccess }: LmsMappingModalProps) {
  const [mappings, setMappings] = useState<string[]>(currentMappings);
  const [newMapping, setNewMapping] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanMapping = newMapping.trim().toUpperCase();
    if (!cleanMapping) return;
    
    if (mappings.includes(cleanMapping)) {
      setNewMapping("");
      return;
    }
    
    setMappings([...mappings, cleanMapping]);
    setNewMapping("");
  };

  const handleRemove = (mappingToRemove: string) => {
    setMappings(mappings.filter(m => m !== mappingToRemove));
  };

  const handleSave = async () => {
    const finalMappings = [...mappings];
    const cleanPending = newMapping.trim().toUpperCase();
    
    // If there's something in the input box, add it before saving
    if (cleanPending && !finalMappings.includes(cleanPending)) {
      finalMappings.push(cleanPending);
    }

    setLoading(true);
    setError(null);
    try {
      await updateLmsRoleMappings(role.id, finalMappings);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to save LMS mappings");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      
      <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-xl overflow-hidden">
        <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          <div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-50">LMS Mappings</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Configure LMS roles for <span className="font-mono font-bold text-slate-700 dark:text-slate-300">{role.name}</span>
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200">
              {error}
            </div>
          )}

          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 text-sm rounded-xl flex items-start gap-2 border border-blue-100 dark:border-blue-800">
            <Info className="w-4 h-4 mt-0.5 shrink-0" />
            <p>
              When a user with <b>{role.name}</b> logs into the LMS, they will automatically be granted the roles listed below. Typical LMS roles are STUDENT, TEACHER, and ADMIN.
            </p>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Mapped Roles
            </label>
            <div className="flex flex-wrap gap-2 mb-4">
              {mappings.map((mapping) => (
                <div key={mapping} className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 border border-purple-200 dark:border-purple-800/50 rounded-lg">
                  <span className="font-mono text-sm font-bold">{mapping}</span>
                  <button 
                    onClick={() => handleRemove(mapping)}
                    className="p-0.5 hover:bg-purple-200 dark:hover:bg-purple-800 rounded-md transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              {mappings.length === 0 && (
                <p className="text-sm text-slate-400 italic">No roles mapped. Users will default to STUDENT.</p>
              )}
            </div>

            <form onSubmit={handleAdd} className="flex items-center gap-2">
              <input
                type="text"
                value={newMapping}
                onChange={(e) => setNewMapping(e.target.value)}
                placeholder="Add LMS role (e.g. TEACHER)"
                className="flex-1 px-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-50 uppercase"
              />
              <button
                type="submit"
                disabled={!newMapping.trim()}
                className="p-2.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl font-medium transition-colors disabled:opacity-50"
              >
                <Plus className="w-5 h-5" />
              </button>
            </form>
          </div>

          <div className="pt-6 flex justify-end gap-3 border-t border-slate-200 dark:border-slate-800">
            <button
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl font-medium transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={loading}
              className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-colors shadow-sm disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Mappings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
