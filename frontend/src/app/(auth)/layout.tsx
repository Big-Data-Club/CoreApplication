import Background from "@/components/layout/Background";
import Footer from "@/components/layout/Footer";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";

type DashboardLayoutProps = {
  children: React.ReactNode;
};

export default async function DashboardLayout({ children }: DashboardLayoutProps) {
  const cookieStore = await cookies();
  const token = cookieStore.get("authToken")?.value;
  if (token) {
    redirect("/");
  }

  return (
    <div className="relative w-full h-screen bg-transparent">
      <Background /> 
      <div className="flex flex-col h-screen bg-transparent">
        <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden bg-transparent no-scrollbar pb-24">
          <main className="flex-1 w-full bg-transparent">
            {children}
          </main>
        </div>
      </div>
      <Footer />
    </div>
  );
}