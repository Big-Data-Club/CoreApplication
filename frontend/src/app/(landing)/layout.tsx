import Background from "@/components/layout/Background";
import Footer from "@/components/layout/Footer";
type LandingLayoutProps = {
  children: React.ReactNode;
};

export default async function LandingLayout({ children }: LandingLayoutProps) {
  return (
    <div className="relative w-full bg-transparent">
      <Background /> 
      <div className="flex flex-col min-h-screen bg-transparent">
        <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden bg-transparent no-scrollbar pb-24">
          <main className="flex-1 p-4 lg:p-8 bg-transparent">
            {children}
          </main>
        </div>
      </div>
      <Footer />
    </div>
  );
}