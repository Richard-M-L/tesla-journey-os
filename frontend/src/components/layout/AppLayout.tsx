import { type ReactNode } from "react";
import { Sidebar } from "./Sidebar";

interface Props {
  children: ReactNode;
}

export function AppLayout({ children }: Props) {
  return (
    <div className="flex h-screen overflow-hidden bg-tesla-gray-900">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        {children}
      </main>
    </div>
  );
}
