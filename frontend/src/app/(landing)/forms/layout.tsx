import { Logo } from "@/components/layout/Logo";

export default function FormsLayout({ children }) {
  return (
    <div className="relative w-full bg-transparent">
      <div className="flex flex-col min-h-screen bg-transparent">
        <div className="flex-1 overflow-y-auto bg-transparent">
          <header className="border-b-4 border-double border-[#2c2416] bg-transparent shadow-sm">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Logo />
                <div>
                  <h2 className="text-xl lg:text-2xl font-bold text-[#2c2416]">
                    Big Data Club
                  </h2>
                  <p className="text-xs lg:text-sm text-[#5a4a3a] italic">
                    Think Big • Speak Data
                  </p>
                </div>
              </div>
            </div>
          </header>
          {children}
        </div>
      </div>
    </div>
  );
}