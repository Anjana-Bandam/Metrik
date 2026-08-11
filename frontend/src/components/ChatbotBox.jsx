// import React from "react";
// import { Sparkles } from "lucide-react";

// /** Permanent AI narrative box — context-aware paragraph, decision-support tone. */
// export default function ChatbotBox({ narrative, loading }) {
//   return (
//     <div className="glass-panel p-4 flex gap-3">
//       <div className="w-8 h-8 rounded-lg grid place-items-center bg-amber-500/12 text-amber-500 shrink-0">
//         <Sparkles size={15} />
//       </div>
//       <div className="min-w-0">
//         <p className="text-xs font-medium uppercase tracking-wide text-graphite-500 dark:text-mist-300/50 mb-1">
//           Metrik narrative
//         </p>
//         {loading ? (
//           <div className="space-y-2 pt-1">
//             <div className="h-2.5 rounded bg-mist-200/70 dark:bg-graphite-700/70 animate-pulse w-full" />
//             <div className="h-2.5 rounded bg-mist-200/70 dark:bg-graphite-700/70 animate-pulse w-4/5" />
//           </div>
//         ) : (
//           <p className="text-sm leading-relaxed text-graphite-700 dark:text-mist-200">
//             {narrative}
//           </p>
//         )}
//       </div>
//     </div>
//   );
// }
