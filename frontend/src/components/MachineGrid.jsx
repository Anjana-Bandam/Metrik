import React from "react";
import { Plus } from "lucide-react";
import MachineCard from "./MachineCard.jsx";

export default function MachineGrid({ machines, onOpen, onAddClick, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="card p-5 h-[268px]">
            <div className="skeleton h-4 w-1/2 mb-3" />
            <div className="skeleton h-10 w-1/3 mb-4" />
            <div className="skeleton h-1.5 w-full mb-6" />
            <div className="skeleton h-8 w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {machines.map((m) => (
        <MachineCard key={m.machine_id} machine={m} onOpen={onOpen} />
      ))}

      <button onClick={onAddClick}
        className="min-h-[268px] rounded-card border-2 border-dashed
                   border-cream-300 dark:border-white/[0.1]
                   flex flex-col items-center justify-center gap-3 t-faint
                   hover:text-lime-600 dark:hover:text-lime-300
                   hover:border-lime-400 transition-colors animate-rise">
        <div className="w-12 h-12 rounded-pill grid place-items-center bg-cream-200 dark:bg-ink-700">
          <Plus size={20} />
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold">Connect a machine</p>
          <p className="text-xs t-faint mt-0.5">OPC UA · MTConnect · FOCAS · Retrofit</p>
        </div>
      </button>
    </div>
  );
}