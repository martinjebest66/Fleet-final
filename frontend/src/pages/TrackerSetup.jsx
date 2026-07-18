import { Cpu, NumberOne, NumberTwo, NumberThree, NumberFour, NumberFive, Check, Copy, Info } from "@phosphor-icons/react";
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { toast } from "sonner";

export default function TrackerSetup() {
  const [tcpStatus, setTcpStatus] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/gps/tcp-status`, { withCredentials: true });
      setTcpStatus(res.data);
    } catch { toast.error("Nepodařilo se načíst stav serveru"); }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Zkopírováno do schránky");
  };

  return (
    <div className="space-y-8 max-w-4xl" data-testid="tracker-setup-page">
      <div>
        <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Nastavení GPS trackeru</h1>
        <p className="text-[#52525B] mt-1">Teltonika FMB003 — návod na propojení s Fleet Managerem</p>
      </div>

      {/* Server status */}
      {tcpStatus && (
        <div className={`border rounded-md p-4 flex items-center gap-3 ${tcpStatus.running ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
          <div className={`w-3 h-3 rounded-full ${tcpStatus.running ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          <div>
            <p className="font-medium text-[#18181B]">TCP server: {tcpStatus.running ? "Aktivní" : "Neaktivní"}</p>
            <p className="text-sm text-[#52525B]">Port {tcpStatus.port} | Codec 8 / 8 Extended</p>
          </div>
        </div>
      )}

      {/* Prerequisites */}
      <div className="bg-blue-50 border border-blue-200 rounded-md p-5">
        <div className="flex items-start gap-3">
          <Info size={20} className="text-blue-600 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-900">Co budete potřebovat</h3>
            <ul className="text-sm text-blue-800 mt-2 space-y-1 list-disc list-inside">
              <li>Teltonika FMB003 GPS tracker</li>
              <li>Teltonika Configurator (stáhnete z <span className="font-mono">wiki.teltonika-gps.com</span>)</li>
              <li>USB kabel nebo Bluetooth připojení k trackeru</li>
              <li>SIM karta s datovým tarifem (aktivní APN)</li>
              <li>Veřejnou IP adresu nebo doménu serveru</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-6">
        {/* Step 1 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#002FA7] text-white rounded-full flex items-center justify-center font-bold text-sm">1</div>
            <h2 className="font-semibold text-lg text-[#18181B]">Připojte tracker k Configuratoru</h2>
          </div>
          <ol className="text-sm text-[#52525B] space-y-2 ml-11 list-decimal">
            <li>Stáhněte a nainstalujte <strong>Teltonika Configurator</strong></li>
            <li>Připojte FMB003 přes <strong>USB</strong> nebo <strong>Bluetooth</strong></li>
            <li>Klikněte <strong>&ldquo;Load from device&rdquo;</strong> pro načtení aktuální konfigurace</li>
          </ol>
        </div>

        {/* Step 2 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#002FA7] text-white rounded-full flex items-center justify-center font-bold text-sm">2</div>
            <h2 className="font-semibold text-lg text-[#18181B]">Nastavte GPRS a SIM kartu</h2>
          </div>
          <div className="ml-11 text-sm text-[#52525B] space-y-2">
            <p>V sekci <strong>GPRS → GPRS Settings</strong>:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><strong>APN</strong>: Zadejte APN vašeho operátora (např. <span className="font-mono bg-[#F4F4F5] px-1 rounded">internet</span>)</li>
              <li><strong>GPRS Context</strong>: Zapnuto</li>
            </ul>
          </div>
        </div>

        {/* Step 3 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#002FA7] text-white rounded-full flex items-center justify-center font-bold text-sm">3</div>
            <h2 className="font-semibold text-lg text-[#18181B]">Nastavte dual server (Ruhavik + Fleet Manager)</h2>
          </div>
          <div className="ml-11 space-y-4">
            <div>
              <p className="text-sm text-[#52525B] mb-3">V sekci <strong>GPRS → Server Settings</strong>:</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-[#F4F4F5] rounded-md p-4">
                  <p className="font-semibold text-[#18181B] mb-2">Server 1 (Ruhavik)</p>
                  <div className="text-sm space-y-1 font-mono">
                    <p>Domain: <span className="text-[#002FA7]">vaše Ruhavik adresa</span></p>
                    <p>Port: <span className="text-[#002FA7]">vaše Ruhavik port</span></p>
                    <p>Protocol: <span className="text-[#002FA7]">TCP</span></p>
                  </div>
                </div>
                <div className="bg-[#002FA7]/5 border border-[#002FA7]/20 rounded-md p-4">
                  <p className="font-semibold text-[#002FA7] mb-2">Server 2 (Fleet Manager)</p>
                  <div className="text-sm space-y-1 font-mono">
                    <div className="flex items-center gap-2">
                      <span>Domain:</span>
                      <span className="text-[#002FA7] font-bold">vaše_veřejná_IP</span>
                      <button onClick={() => copyToClipboard("vaše_veřejná_IP")} className="text-[#A1A1AA] hover:text-[#002FA7]"><Copy size={14} /></button>
                    </div>
                    <div className="flex items-center gap-2">
                      <span>Port:</span>
                      <span className="text-[#002FA7] font-bold">{tcpStatus?.port || 5027}</span>
                      <button onClick={() => copyToClipboard(String(tcpStatus?.port || 5027))} className="text-[#A1A1AA] hover:text-[#002FA7]"><Copy size={14} /></button>
                    </div>
                    <p>Protocol: <span className="text-[#002FA7] font-bold">TCP</span></p>
                  </div>
                </div>
              </div>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3">
              <p className="text-sm text-amber-800"><strong>Backup Mode:</strong> Vyberte <strong>&ldquo;Duplicate&rdquo;</strong> — data se posílají na oba servery současně. Smaží se až po potvrzení obou.</p>
            </div>
          </div>
        </div>

        {/* Step 4 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#002FA7] text-white rounded-full flex items-center justify-center font-bold text-sm">4</div>
            <h2 className="font-semibold text-lg text-[#18181B]">Zapněte OBD-II data a Codec 8 Extended</h2>
          </div>
          <div className="ml-11 text-sm text-[#52525B] space-y-3">
            <p>V sekci <strong>Data Protocol</strong>:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Nastavte <strong>Codec 8 Extended</strong> (Param ID 113 = 1)</li>
            </ul>
            <p className="mt-2">V sekci <strong>OBD-II → OBD Parameters</strong> zapněte:</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-2">
              {[
                { name: "Engine RPM", id: "AVL ID 36" },
                { name: "Coolant Temp", id: "AVL ID 32" },
                { name: "Fuel Level", id: "AVL ID 48" },
                { name: "OEM Fuel Level", id: "AVL ID 390" },
                { name: "DTC Count", id: "AVL ID 30" },
                { name: "Engine Load", id: "AVL ID 38" },
                { name: "Throttle Position", id: "AVL ID 37" },
                { name: "Battery Voltage", id: "AVL ID 67" },
                { name: "Total Odometer", id: "AVL ID 16" },
              ].map(p => (
                <div key={p.id} className="bg-[#F4F4F5] rounded px-3 py-2">
                  <p className="font-medium text-[#18181B] text-xs">{p.name}</p>
                  <p className="font-mono text-[10px] text-[#A1A1AA]">{p.id}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-[#A1A1AA] mt-2">Nastavte prioritu na 1+ (Low) u každého parametru</p>
          </div>
        </div>

        {/* Step 5 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#002FA7] text-white rounded-full flex items-center justify-center font-bold text-sm">5</div>
            <h2 className="font-semibold text-lg text-[#18181B]">Zaregistrujte tracker v aplikaci</h2>
          </div>
          <div className="ml-11 text-sm text-[#52525B] space-y-2">
            <ol className="list-decimal space-y-1">
              <li>Jděte na <strong>GPS sledování → Trackery</strong></li>
              <li>Klikněte <strong>&ldquo;Přidat tracker&rdquo;</strong></li>
              <li>Zadejte <strong>IMEI</strong> číslo (15 číslic na štítku trackeru)</li>
              <li>Vyberte <strong>vozidlo</strong> ke kterému tracker patří</li>
              <li>Klikněte <strong>&ldquo;Registrovat&rdquo;</strong></li>
            </ol>
            <p className="mt-3">IMEI najdete na štítku trackeru nebo v Configuratoru v sekci <strong>Status → Device Info</strong>.</p>
          </div>
        </div>

        {/* Step 6 */}
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-[#16A34A] text-white rounded-full flex items-center justify-center"><Check size={18} weight="bold" /></div>
            <h2 className="font-semibold text-lg text-[#18181B]">Hotovo!</h2>
          </div>
          <div className="ml-11 text-sm text-[#52525B] space-y-2">
            <p>Po uložení konfigurace a připojení trackeru k OBD portu vozidla:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><strong>Live mapa</strong> — pozice vozidla v reálném čase</li>
              <li><strong>OBD diagnostika</strong> — otáčky, teplota, palivo, napětí baterie</li>
              <li><strong>Auto-detekce jízd</strong> — automatické záznamy do knihy jízd</li>
              <li><strong>Ruhavik</strong> — funguje dál paralelně beze změny</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Data overview */}
      <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
        <h2 className="font-semibold text-lg text-[#18181B] mb-4">Jaká data přijímáme z FMB003</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E4E4E7]">
                <th className="text-left py-2 text-[#52525B] font-medium">Kategorie</th>
                <th className="text-left py-2 text-[#52525B] font-medium">Parametry</th>
                <th className="text-left py-2 text-[#52525B] font-medium">Využití</th>
              </tr>
            </thead>
            <tbody className="text-[#18181B]">
              <tr className="border-b border-[#E4E4E7]"><td className="py-2 font-medium">GPS</td><td>Lat, Lng, nadmořská výška, satelity</td><td>Live mapa, historie tras</td></tr>
              <tr className="border-b border-[#E4E4E7]"><td className="py-2 font-medium">Pohyb</td><td>Rychlost, směr, ignition</td><td>Detekce jízdy, statistiky</td></tr>
              <tr className="border-b border-[#E4E4E7]"><td className="py-2 font-medium">Motor</td><td>Otáčky, teplota chladiva, zátěž</td><td>Diagnostika</td></tr>
              <tr className="border-b border-[#E4E4E7]"><td className="py-2 font-medium">Palivo</td><td>Stav paliva (%), spotřeba (l/h)</td><td>Analytika spotřeby</td></tr>
              <tr className="border-b border-[#E4E4E7]"><td className="py-2 font-medium">Diagnostika</td><td>DTC kódy, MIL kontrolka</td><td>Závady vozidla</td></tr>
              <tr><td className="py-2 font-medium">Baterie</td><td>Napětí ext. + interní</td><td>Stav vozidla</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
