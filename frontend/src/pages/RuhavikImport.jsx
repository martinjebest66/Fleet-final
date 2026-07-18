import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API } from "../App";
import { MapPin, UploadSimple, FileArrowUp, CheckCircle, Info } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";

export default function RuhavikImport() {
  const [vehicles, setVehicles] = useState([]);
  const [vehicleId, setVehicleId] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);

  const fetchVehicles = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/vehicles`, { withCredentials: true });
      setVehicles(res.data);
    } catch { toast.error("Nepodařilo se načíst vozidla"); }
  }, []);

  useEffect(() => { fetchVehicles(); }, [fetchVehicles]);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (f) {
      const ext = f.name.toLowerCase();
      if (!ext.endsWith(".csv") && !ext.endsWith(".gpx")) {
        toast.error("Nepodporovaný formát. Nahrajte .csv nebo .gpx soubor.");
        return;
      }
      setFile(f);
      setResult(null);
    }
  };

  const handleImport = async () => {
    if (!vehicleId || !file) {
      toast.error("Vyberte vozidlo a soubor");
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("vehicle_id", vehicleId);
      fd.append("file", file);
      const res = await axios.post(`${API}/gps/import-ruhavik`, fd, {
        withCredentials: true,
        headers: { "Content-Type": "multipart/form-data" }
      });
      setResult(res.data);
      toast.success(res.data.message);
    } catch (err) {
      const msg = err.response?.data?.detail || "Nepodařilo se importovat";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="ruhavik-import-page">
      <div>
        <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">Import z Ruhaviku</h1>
        <p className="text-[#52525B] mt-1">Nahrání historických GPS tras z CSV nebo GPX souboru</p>
      </div>

      {/* Info box */}
      <div className="bg-blue-50 border border-blue-200 rounded-md p-4 flex gap-3">
        <Info size={24} weight="duotone" className="text-blue-600 shrink-0 mt-0.5" />
        <div className="text-sm text-blue-800">
          <p className="font-semibold mb-1">Podporované formáty</p>
          <ul className="list-disc list-inside space-y-1">
            <li><strong>GPX</strong> — standardní formát GPS tras (doporučeno)</li>
            <li><strong>CSV</strong> — export z Ruhaviku se sloupci: latitude, longitude, timestamp, speed</li>
          </ul>
          <p className="mt-2">Trasy budou automaticky rozděleny podle časových mezer (15+ minut = nová trasa).</p>
        </div>
      </div>

      {/* Upload form */}
      <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
        <div className="space-y-4 max-w-lg">
          <div>
            <Label>Vozidlo *</Label>
            <Select value={vehicleId} onValueChange={setVehicleId}>
              <SelectTrigger data-testid="ruhavik-vehicle-select"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
              <SelectContent>
                {vehicles.map(v => (
                  <SelectItem key={v.vehicle_id} value={v.vehicle_id}>
                    {v.brand} {v.model} ({v.registration_plate})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Soubor (CSV / GPX) *</Label>
            <div className="mt-1">
              <label
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-[#E4E4E7] rounded-md cursor-pointer hover:border-[#002FA7] hover:bg-blue-50/30 transition-colors"
                data-testid="ruhavik-file-dropzone"
              >
                <FileArrowUp size={32} weight="duotone" className="text-[#A1A1AA] mb-2" />
                <span className="text-sm text-[#52525B]">
                  {file ? file.name : "Klikněte pro výběr souboru"}
                </span>
                {file && <span className="text-xs text-[#A1A1AA] mt-1">{(file.size / 1024).toFixed(1)} KB</span>}
                <input type="file" accept=".csv,.gpx" onChange={handleFileChange} className="hidden" data-testid="ruhavik-file-input" />
              </label>
            </div>
          </div>

          <Button
            onClick={handleImport}
            disabled={!vehicleId || !file || uploading}
            className="bg-[#002FA7] hover:bg-[#002480] w-full"
            data-testid="ruhavik-import-btn"
          >
            {uploading ? (
              <><div className="loading-spinner w-4 h-4 mr-2"></div>Importuji...</>
            ) : (
              <><UploadSimple size={20} className="mr-2" />Importovat trasy</>
            )}
          </Button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-md p-6" data-testid="ruhavik-import-result">
          <div className="flex items-start gap-3">
            <CheckCircle size={28} weight="duotone" className="text-emerald-600 shrink-0" />
            <div>
              <h3 className="font-semibold text-emerald-800">{result.message}</h3>
              <div className="mt-2 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-emerald-600">GPS bodů zpracováno</p>
                  <p className="text-lg font-bold text-emerald-800">{result.points_count}</p>
                </div>
                <div>
                  <p className="text-emerald-600">Tras vytvořeno</p>
                  <p className="text-lg font-bold text-emerald-800">{result.trips_count}</p>
                </div>
              </div>
              <p className="text-xs text-emerald-600 mt-3">
                Trasy najdete na stránce GPS sledování. Odtud je můžete synchronizovat do knihy jízd.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* How to export from Ruhavik */}
      <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
        <h3 className="font-['Manrope'] text-lg font-semibold text-[#18181B] mb-3">Jak exportovat z Ruhaviku?</h3>
        <ol className="space-y-3 text-sm text-[#52525B]">
          <li className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-[#002FA7] text-white flex items-center justify-center text-xs font-bold">1</span>
            <span>Otevřete aplikaci <strong>Ruhavik</strong> na svém telefonu</span>
          </li>
          <li className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-[#002FA7] text-white flex items-center justify-center text-xs font-bold">2</span>
            <span>Přejděte na <strong>Historie tras</strong> a vyberte požadované období</span>
          </li>
          <li className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-[#002FA7] text-white flex items-center justify-center text-xs font-bold">3</span>
            <span>Klikněte na <strong>Export</strong> a zvolte formát <strong>GPX</strong> (doporučeno) nebo <strong>CSV</strong></span>
          </li>
          <li className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-[#002FA7] text-white flex items-center justify-center text-xs font-bold">4</span>
            <span>Soubor přeneste do počítače a nahrajte ho výše</span>
          </li>
        </ol>
      </div>
    </div>
  );
}
