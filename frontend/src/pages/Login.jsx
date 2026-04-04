import { SignIn } from "@phosphor-icons/react";

export default function Login() {
  const handleGoogleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left side - Image */}
      <div 
        className="hidden lg:flex lg:w-1/2 bg-cover bg-center relative"
        style={{
          backgroundImage: "url('https://images.unsplash.com/photo-1504366130991-154787072d46?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTB8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBjYXJ8ZW58MHx8fHwxNzc1MjkxNDQzfDA&ixlib=rb-4.1.0&q=85')"
        }}
      >
        <div className="absolute inset-0 bg-black/40" />
        <div className="relative z-10 flex flex-col justify-end p-12 text-white">
          <h2 className="font-['Manrope'] text-4xl font-bold tracking-tight mb-4">
            Fleet Manager
          </h2>
          <p className="text-lg text-white/80 max-w-md">
            Komplexní správa vozového parku pro autoškoly. Sledujte jízdy, tankování, poškození a GPS data na jednom místě.
          </p>
        </div>
      </div>

      {/* Right side - Login form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <div className="text-center mb-10">
            <h1 className="font-['Manrope'] text-3xl font-bold text-[#18181B] tracking-tight mb-2">
              Vítejte zpět
            </h1>
            <p className="text-[#52525B]">
              Přihlaste se pro přístup do systému
            </p>
          </div>

          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 bg-[#002FA7] hover:bg-[#002480] text-white font-semibold py-4 px-6 rounded-md transition-colors duration-200 btn-active"
            data-testid="google-login-btn"
          >
            <SignIn size={24} weight="bold" />
            <span>Přihlásit se přes Google</span>
          </button>

          <div className="mt-8 text-center">
            <p className="text-sm text-[#52525B]">
              Přihlášením souhlasíte s podmínkami použití
            </p>
          </div>

          {/* Mobile branding */}
          <div className="lg:hidden mt-12 text-center">
            <h2 className="font-['Manrope'] text-xl font-bold text-[#18181B]">
              Fleet Manager
            </h2>
            <p className="text-sm text-[#52525B] mt-1">
              Správa vozového parku pro autoškoly
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
