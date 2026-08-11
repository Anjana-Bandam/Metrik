import React from "react";
import Header from "../components/Header.jsx";
import SimulatorPanel from "../components/SimulatorPanel.jsx";

export default function SimulationPage() {
  return (
    <div className="flex-1 min-w-0">
      <Header title="Job planner"
        subtitle="Test cutting parameters before the job runs — sandbox only" />
      <div className="p-5 md:p-8">
        <SimulatorPanel />
      </div>
    </div>
  );
}