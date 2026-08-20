import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { API, useAuth } from "../App";
import { errorMessage } from "@/lib/api";
import { SignIn, Key, UserCircle, EnvelopeSimple, Lock } from "@phosphor-icons/react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

export default function Login() {
  const navigate = useNavigate();
  const { setUser, user } = useAuth();
  const [tab, setTab] = useState("admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [instructors, setInstructors] = useState([]);
  const [selectedInstructor, setSelectedInstructor] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  const fetchInstructors = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/auth/instructors-list`);
      setInstructors(res.data);
    } catch (err) {
      // `toast` was never imported here: this handler used to throw a
      // ReferenceError, so a failed instructor lookup left the dropdown empty
      // with no message at all.
      setError(errorMessage(err, "Nepodařilo se načíst seznam instruktorů"));
    }
  }, []);

  useEffect(() => {
    if (tab === "instructor") fetchInstructors();
  }, [tab, fetchInstructors]);

  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleAdminLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/login`, { email, password }, { withCredentials: true });
      setUser(res.data);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || "Nepodařilo se přihlásit");
    } finally {
      setLoading(false);
    }
  };

  const handleInstructorLogin = async (e) => {
    e.preventDefault();
    setError("");
    if (!selectedInstructor || !pin) {
      setError("Vyberte instruktora a zadejte PIN");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/instructor-login`, { instructor_id: selectedInstructor, pin }, { withCredentials: true });
      setUser(res.data);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || "Nepodařilo se přihlásit");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left side */}
      <div
        className="hidden lg:flex lg:w-1/2 bg-cover bg-center relative"
        style={{ backgroundImage: "url('https://images.unsplash.com/photo-1504366130991-154787072d46?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTB8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBjYXJ8ZW58MHx8fHwxNzc1MjkxNDQzfDA&ixlib=rb-4.1.0&q=85')" }}
      >
        <div className="absolute inset-0 bg-black/40" />
        <div className="relative z-10 flex flex-col justify-end p-12 text-white">
          <h2 className="font-['Manrope'] text-4xl font-bold tracking-tight mb-4">Fleet Manager</h2>
          <p className="text-lg text-white/80 max-w-md">
            Komplexní správa vozového parku pro autoškoly. Sledujte jízdy, tankování, poškození a GPS data na jednom místě.
          </p>
        </div>
      </div>

      {/* Right side */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="font-['Manrope'] text-3xl font-bold text-[#18181B] tracking-tight mb-2">Vítejte zpět</h1>
            <p className="text-[#52525B]">Přihlaste se pro přístup do systému</p>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 bg-[#F4F4F5] p-1 rounded-lg mb-6">
            <button
              onClick={() => { setTab("admin"); setError(""); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-all ${tab === "admin" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`}
              data-testid="tab-admin"
            >
              <UserCircle size={18} />
              Admin
            </button>
            <button
              onClick={() => { setTab("instructor"); setError(""); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-all ${tab === "instructor" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`}
              data-testid="tab-instructor"
            >
              <Key size={18} />
              Instruktor
            </button>
          </div>

          {/* Admin Tab */}
          {tab === "admin" && (
            <div className="space-y-4">
              <form onSubmit={handleAdminLogin} className="space-y-4">
                <div>
                  <Label htmlFor="email">E-mail</Label>
                  <div className="relative mt-1">
                    <EnvelopeSimple size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]" />
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin@autoskola.cz"
                      className="pl-10"
                      required
                      data-testid="admin-email-input"
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="password">Heslo</Label>
                  <div className="relative mt-1">
                    <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]" />
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Zadejte heslo"
                      className="pl-10"
                      required
                      data-testid="admin-password-input"
                    />
                  </div>
                </div>
                <Button type="submit" className="w-full bg-[#002FA7] hover:bg-[#002480] py-6" disabled={loading} data-testid="admin-login-btn">
                  {loading ? <div className="loading-spinner w-5 h-5 mr-2"></div> : <SignIn size={20} className="mr-2" />}
                  Přihlásit se
                </Button>
              </form>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-[#E4E4E7]"></div></div>
                <div className="relative flex justify-center"><span className="bg-white px-3 text-sm text-[#A1A1AA]">nebo</span></div>
              </div>

              <button
                onClick={handleGoogleLogin}
                className="w-full flex items-center justify-center gap-3 border border-[#E4E4E7] text-[#18181B] font-medium py-3.5 px-6 rounded-md transition-colors duration-200 hover:bg-[#F4F4F5]"
                data-testid="google-login-btn"
              >
                <svg width="20" height="20" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                Přihlásit přes Google
              </button>
            </div>
          )}

          {/* Instructor Tab */}
          {tab === "instructor" && (
            <form onSubmit={handleInstructorLogin} className="space-y-4">
              <div>
                <Label>Instruktor</Label>
                <Select value={selectedInstructor} onValueChange={setSelectedInstructor}>
                  <SelectTrigger className="mt-1" data-testid="instructor-select">
                    <SelectValue placeholder="Vyberte své jméno" />
                  </SelectTrigger>
                  <SelectContent>
                    {instructors.map(i => (
                      <SelectItem key={i.instructor_id} value={i.instructor_id}>{i.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {instructors.length === 0 && (
                  <p className="text-xs text-[#A1A1AA] mt-1">Žádní instruktoři s PINem</p>
                )}
              </div>
              <div>
                <Label htmlFor="pin">PIN kód</Label>
                <div className="relative mt-1">
                  <Key size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]" />
                  <Input
                    id="pin"
                    type="password"
                    inputMode="numeric"
                    maxLength={6}
                    value={pin}
                    onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                    placeholder="Zadejte 4-6 místný PIN"
                    className="pl-10 text-center text-xl tracking-[0.5em] font-mono"
                    required
                    data-testid="instructor-pin-input"
                  />
                </div>
              </div>
              <Button type="submit" className="w-full bg-[#002FA7] hover:bg-[#002480] py-6" disabled={loading || !selectedInstructor} data-testid="instructor-login-btn">
                {loading ? <div className="loading-spinner w-5 h-5 mr-2"></div> : <Key size={20} className="mr-2" />}
                Přihlásit se
              </Button>
            </form>
          )}

          {/* Error */}
          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700" data-testid="login-error">
              {error}
            </div>
          )}

          <div className="mt-8 text-center">
            <p className="text-sm text-[#52525B]">Přihlášením souhlasíte s podmínkami použití</p>
          </div>

          <div className="lg:hidden mt-12 text-center">
            <h2 className="font-['Manrope'] text-xl font-bold text-[#18181B]">Fleet Manager</h2>
            <p className="text-sm text-[#52525B] mt-1">Správa vozového parku pro autoškoly</p>
          </div>
        </div>
      </div>
    </div>
  );
}
