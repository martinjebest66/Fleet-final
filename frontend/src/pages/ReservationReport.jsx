import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API, useAuth } from "../App";
import { errorMessage } from "@/lib/api";
import { UploadSimple, Path, Warning, CheckCircle, MapPinLine, Trash, ArrowClockwise, EyeSlash, CalendarPlus } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";

export default function ReservationReport() {
  const { user } = useAuth();
  const isAdmin = user?.role !== "instructor";
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [batches, setBatches] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [drives, setDrives] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [icsStatus, setIcsStatus] = useState(null);

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [vehicleId, setVehicleId] = useState("all");
  const [onlyExceeded, setOnlyExceeded] = useState(false);

  const fetchVehicles = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/vehicles`, { withCredentials: true });
      setVehicles(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchBatches = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/reservations/batches`, { withCredentials: true });
      setBatches(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchIcsStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/reservations/ics-status`, { withCredentials: true });
      setIcsStatus(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchDrives = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (vehicleId && vehicleId !== "all") params.vehicle_id = vehicleId;
      if (onlyExceeded) params.only_exceeded = true;
      const res = await axios.get(`${API}/reservations/drives`, { params, withCredentials: true });
      setDrives(res.data.drives);
      setSummary(res.data.summary);
    } catch {
      toast.error("Nepodařilo se načíst jízdy");
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, vehicleId, onlyExceeded]);

  useEffect(() => { fetchVehicles(); fetchBatches(); fetchIcsStatus(); }, [fetchVehicles, fetchBatches, fetchIcsStatus]);
  useEffect(() => { fetchDrives(); }, [fetchDrives]);

  const handleImport = async () => {
    if (!file) { toast.error("Vyberte soubor s exportem"); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/reservations/import`, fd, {
        withCredentials: true,
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Naimportováno ${res.data.imported} jízd (${res.data.vehicles.length} vozidel)`);
      setFile(null);
      fetchBatches();
      fetchDrives();
    } catch (err) {
      toast.error(errorMessage(err, "Import se nezdařil"));
    } finally {
      setUploading(false);
    }
  };

  const handleSyncIcs = async () => {
    setSyncing(true);
    try {
      const res = await axios.post(`${API}/reservations/sync-ics`, {}, { withCredentials: true });
      if (res.data.started === false && res.data.running) {
        toast.info("Synchronizace už probíhá");
      } else {
        toast.info("Synchronizace kalendářů spuštěna…");
      }
      // poll status until finished
      let done = false;
      for (let i = 0; i < 40 && !done; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const st = await axios.get(`${API}/reservations/ics-status`, { withCredentials: true });
        setIcsStatus(st.data);
        if (!st.data.running) {
          done = true;
          const s = st.data.status || {};
          const errs = (s.results || []).filter((r) => r.error);
          toast.success(`Synchronizováno ${s.total_events ?? 0} jízd z ${s.synced ?? 0} kalendářů`);
          if (errs.length) toast.error(`Chyby: ${errs.map((e) => `${e.instructor}: ${e.error}`).join(", ")}`);
        }
      }
      fetchBatches();
      fetchDrives();
      fetchIcsStatus();
    } catch (err) {
      toast.error(errorMessage(err, "Synchronizace se nezdařila"));
    } finally {
      setSyncing(false);
    }
  };

  const deleteBatch = async (batchId) => {
    if (!window.confirm("Opravdu smazat tento import a všechny jeho jízdy?")) return;
    try {
      await axios.delete(`${API}/reservations/batches/${batchId}`, { withCredentials: true });
      toast.success("Import smazán");
      fetchBatches();
      fetchDrives();
    } catch {
      toast.error("Nepodařilo se smazat");
    }
  };

  const togglePrivate = async (drive) => {
    try {
      const res = await axios.patch(
        `${API}/reservations/drives/${drive.drive_id}/private`,
        { is_private: !drive.is_private },
        { withCredentials: true }
      );
      setDrives((prev) => prev.map((d) => d.drive_id === drive.drive_id
        ? { ...d, is_private: res.data.is_private, route_hidden: res.data.is_private }
        : d));
    } catch (err) {
      toast.error(errorMessage(err, "Nepodařilo se změnit soukromí"));
    }
  };

  const fmtDateTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("cs-CZ", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  };
  const num = (v, unit = "") => (v === null || v === undefined ? "—" : `${v}${unit}`);

  return (
    <div className="max-w-[1400px] mx-auto space-y-6" data-testid="reservation-report-page">
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-[#002FA7]/10 flex items-center justify-center">
          <Path size={24} weight="duotone" className="text-[#002FA7]" />
        </div>
        <div>
          <h1 className="font-['Manrope'] text-2xl font-bold text-[#18181B]">Report ujetých km</h1>
          <p className="text-sm text-[#52525B]">Skutečné km z GPS na jízdu, tolerance přejezdů a upozornění na překročení limitu</p>
        </div>
      </div>

      {/* Import */}
      {isAdmin && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <UploadSimple size={18} weight="duotone" /> Načtení jízd
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-[#002FA7]/5 rounded-xl p-4">
              <div className="flex-1">
                <p className="text-sm font-semibold text-[#18181B] flex items-center gap-1.5"><CalendarPlus size={16} weight="duotone" /> Synchronizace z kalendáře (ICS)</p>
                <p className="text-xs text-[#71717A] mt-0.5">Načte aktuální jízdy z kalendářů učitelů (ICS odkaz nastavíte u instruktora).</p>
                {icsStatus && (
                  <p className="text-[11px] text-[#A1A1AA] mt-1">
                    {icsStatus.auto_sync ? `Automaticky každých ${icsStatus.interval_minutes} min` : "Automatická synchronizace vypnutá"}
                    {icsStatus.status?.last_run && ` · naposledy ${new Date(icsStatus.status.last_run).toLocaleString("cs-CZ", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`}
                  </p>
                )}
              </div>
              <Button onClick={handleSyncIcs} disabled={syncing} data-testid="sync-ics-btn">
                <ArrowClockwise size={16} weight="bold" className="mr-1" /> {syncing ? "Synchronizuji…" : "Synchronizovat kalendáře"}
              </Button>
            </div>
            <div className="flex items-center gap-3">
              <div className="h-px bg-[#E4E4E7] flex-1" />
              <span className="text-xs text-[#A1A1AA]">nebo nahrát export (.xls)</span>
              <div className="h-px bg-[#E4E4E7] flex-1" />
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
              <input
                type="file"
                accept=".xls,.xlsx,.html,.htm"
                onChange={(e) => setFile(e.target.files[0] || null)}
                data-testid="reservation-file-input"
                className="text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-[#002FA7]/10 file:text-[#002FA7] file:font-medium file:cursor-pointer"
              />
              <Button onClick={handleImport} disabled={uploading || !file} data-testid="reservation-import-btn">
                {uploading ? "Importuji…" : "Importovat"}
              </Button>
            </div>
            {batches.length > 0 && (
              <div className="border-t border-[#E4E4E7] pt-3">
                <p className="text-xs font-semibold text-[#71717A] mb-2 uppercase tracking-wide">Nahrané importy</p>
                <div className="space-y-1">
                  {batches.map((b) => (
                    <div key={b.batch_id} className="flex items-center justify-between text-sm bg-[#FAFAFA] rounded-lg px-3 py-2">
                      <span className="truncate">
                        <span className="font-medium">{b.filename || "export"}</span>
                        <span className="text-[#71717A]"> · {b.count} jízd</span>
                      </span>
                      <button onClick={() => deleteBatch(b.batch_id)} className="text-[#991B1B] hover:bg-red-50 p-1.5 rounded" data-testid={`delete-batch-${b.batch_id}`}>
                        <Trash size={16} weight="duotone" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="kpi-card"><p className="text-sm text-[#71717A]">Jízd celkem</p><p className="text-2xl font-bold text-[#18181B]">{summary.total}</p></div>
          <div className="kpi-card"><p className="text-sm text-[#71717A]">Překročen limit</p><p className="text-2xl font-bold text-[#991B1B]">{summary.exceeded}</p></div>
          <div className="kpi-card"><p className="text-sm text-[#71717A]">Bez GPS dat</p><p className="text-2xl font-bold text-[#A16207]">{summary.missing_gps}</p></div>
          <div className="kpi-card"><p className="text-sm text-[#71717A]">GPS km celkem</p><p className="text-2xl font-bold text-[#002FA7]">{summary.total_gps_km}</p></div>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="py-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-medium text-[#71717A] mb-1">Od</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="filter-date-from" className="border border-[#E4E4E7] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-[#71717A] mb-1">Do</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="filter-date-to" className="border border-[#E4E4E7] rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="min-w-[200px]">
            <label className="block text-xs font-medium text-[#71717A] mb-1">Vozidlo</label>
            <Select value={vehicleId} onValueChange={setVehicleId}>
              <SelectTrigger data-testid="filter-vehicle"><SelectValue placeholder="Všechna vozidla" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Všechna vozidla</SelectItem>
                {vehicles.map((v) => (
                  <SelectItem key={v.vehicle_id} value={v.vehicle_id}>
                    {v.reservation_alias || `${v.brand} ${v.model}`} {v.registration_plate ? `(${v.registration_plate})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm pb-2 cursor-pointer">
            <Switch checked={onlyExceeded} onCheckedChange={setOnlyExceeded} data-testid="filter-only-exceeded" />
            Jen překročené
          </label>
          <Button variant="outline" onClick={fetchDrives} className="ml-auto" data-testid="refresh-btn">
            <ArrowClockwise size={16} weight="bold" className="mr-1" /> Obnovit
          </Button>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm" data-testid="drives-table">
            <thead>
              <tr className="text-left text-[#71717A] border-b border-[#E4E4E7]">
                <th className="px-4 py-3 font-medium">Datum / čas</th>
                <th className="px-4 py-3 font-medium">Učitel</th>
                <th className="px-4 py-3 font-medium">Vozidlo</th>
                <th className="px-4 py-3 font-medium">Stanoviště</th>
                <th className="px-4 py-3 font-medium">Činnost</th>
                <th className="px-4 py-3 font-medium text-right">Rezervace</th>
                <th className="px-4 py-3 font-medium text-right">GPS km</th>
                <th className="px-4 py-3 font-medium text-right">Tolerance</th>
                <th className="px-4 py-3 font-medium text-right">Limit</th>
                <th className="px-4 py-3 font-medium">Stav</th>
                <th className="px-4 py-3 font-medium text-center">Soukromá</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={11} className="px-4 py-8 text-center text-[#71717A]">Načítám…</td></tr>
              )}
              {!loading && drives.length === 0 && (
                <tr><td colSpan={11} className="px-4 py-8 text-center text-[#71717A]">Žádné jízdy. Nahrajte export z rezervačního systému.</td></tr>
              )}
              {!loading && drives.map((d) => (
                <tr key={d.drive_id} className={`border-b border-[#F4F4F5] ${d.exceeded ? "bg-red-50" : ""}`} data-testid={`drive-row-${d.drive_id}`}>
                  <td className="px-4 py-2.5 whitespace-nowrap">{fmtDateTime(d.start_datetime)}</td>
                  <td className="px-4 py-2.5">{d.teacher || "—"}</td>
                  <td className="px-4 py-2.5">{d.vehicle_name || "—"}</td>
                  <td className="px-4 py-2.5">{d.boarding_location || "—"}</td>
                  <td className="px-4 py-2.5"><span className="text-xs px-2 py-0.5 rounded-full bg-[#F4F4F5] text-[#52525B]">{d.activity || "—"}</span></td>
                  <td className="px-4 py-2.5 text-right text-[#71717A]">{num(d.reservation_km, " km")}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">
                    {d.gps_available ? `${d.gps_km} km` : <span className="text-[#A16207] text-xs">chybí GPS</span>}
                    {d.route_hidden && <EyeSlash size={13} className="inline ml-1 text-[#71717A]" />}
                  </td>
                  <td className="px-4 py-2.5 text-right text-[#71717A]">{d.tolerance_km > 0 ? `+${d.tolerance_km}` : "—"}</td>
                  <td className="px-4 py-2.5 text-right">{d.effective_limit_km}</td>
                  <td className="px-4 py-2.5">
                    {!d.gps_available ? <Badge variant="secondary">—</Badge>
                      : d.exceeded
                        ? <Badge className="bg-[#991B1B] hover:bg-[#991B1B]"><Warning size={12} weight="fill" className="mr-1" />Překročeno</Badge>
                        : <Badge className="bg-[#166534] hover:bg-[#166534]"><CheckCircle size={12} weight="fill" className="mr-1" />OK</Badge>}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <Switch checked={!!d.is_private} onCheckedChange={() => togglePrivate(d)} data-testid={`private-switch-${d.drive_id}`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <p className="text-xs text-[#A1A1AA] flex items-center gap-1">
        <MapPinLine size={14} /> Soukromá jízda skryje trasu na mapě, ujeté km zůstanou v reportu.
      </p>
    </div>
  );
}
