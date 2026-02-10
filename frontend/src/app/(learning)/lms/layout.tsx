import { redirect } from "next/navigation";
import Background from "@/components/layout/Background";
import Footer from "@/components/layout/Footer";
import Sidebar from "@/components/layout/Sidebar";
import MobileNav from "@/components/layout/MobileNav";
import { cookies } from "next/headers";

export default async function LMSLayout({ children }: { children: React.ReactNode }) {

  const cookieStore = await cookies();
  const token = cookieStore.get("authToken")?.value;
  if (!token) {
    redirect("/");
  }

  return (
    <div className="relative flex flex-col h-screen w-screen bg-transparent">
      <Background />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-y-auto no-scrollbar overflow-x-hidden bg-transparent">
          <MobileNav />
          <main className="flex-1 p-3 sm:p-4 md:p-6 lg:p-8 bg-transparent w-full">
            {children}
          </main>
        </div>
      </div>
      <Footer />
    </div>
  );
}