import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API, errorMessage } from "@/lib/api";
import { GasPump, Gauge, Info } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { toast } from "sonner";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format, subDays } from "date-fns";

const SOURCE_STYLES = {
  can: "bg-indigo-100 text-indigo-700",
  gps: "bg-blue-100 text-blue-700",
  fuel: "bg-emerald-100 text-emerald-700",
  handover: "bg-violet-100 text-violet-700",
  logbook: "bg-zinc-100 text-zinc-700",
};

const tick = { fontSize: 11 };

/**
 * Odometer and fuel level of one vehicle over time.
 *
 * Answers "what did the car show on that date?" — pick a moment and the
 * dialog reports the odometer and the fuel level together with the record
 * they came from, so a figure extrapolated from tracker distance is never
 * mistaken for a reading somebody wrote down.
 */
export function VehicleStateModal({ open, onOpenChange, vehicle }) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [at, setAt] = useState(today);
  const [range, setRange] = useState({ from: format(subDays(new Date(), 30), "yyyy-MM-dd"), to: today });
  const [state, setState] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);

  const vehicleId = vehicle?.vehicle_id;

  const load = useCallback(async (signal) => {
    if (!vehicleId) return;
    setLoading(true);
    try {
      const [stateRes, historyRes] = await Promise.all([
        axios.get(`${API}/vehicles/${vehicleId}/state?at=${at}`, { withCredentials: true, signal }),
        axios.get(
          `${API}/vehicles/${vehicleId}/state/history?date_from=${range.from}&date_to=${range.to}`,
          { withCredentials: true, signal }
        ),
      ]);
      setState(stateRes.data);
      setHistory(historyRes.data);
    } catch (err) {
      if (axios.isCancel(err) || err.name === "CanceledError") return;
      toast.error(errorMessage(err, "Nepodařilo se načíst stav vozidla"));
    } finally {
      setLoading(false);
    }
  }, [vehicleId, at, range.from, range.to]);

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [open, load]);

  const daily = history?.daily || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Stav vozidla — {vehicle?.brand} {vehicle?.model} ({vehicle?.registration_plate})
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5" data-testid="vehicle-state-modal">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <Label>Stav k datu</Label>
              <Input type="date" value={at} max={today} onChange={(e) => setAt(e.target.value)}
                     data-testid="vehicle-state-date" />
            </div>
            <div>
              <Label>Historie od</Label>
              <Input type="date" value={range.from} max={range.to}
                     onChange={(e) => setRange({ ...range, from: e.target.value })} />
            </div>
            <div>
              <Label>Historie do</Label>
              <Input type="date" value={range.to} max={today}
                     onChange={(e) => setRange({ ...range, to: e.target.value })} />
            </div>
          </div>

          {loading && !state && (
            <div className="flex justify-center py-8"><div className="loading-spinner" /></div>
          )}

          {state && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="border border-[#E4E4E7] rounded-md p-4">
                <p className="text-sm text-[#52525B] flex items-center gap-1">
                  <Gauge size={16} weight="duotone" />Tachometr k {new Date(at).toLocaleDateString("cs-CZ")}
                </p>
                <p className="text-3xl font-bold text-[#18181B]" data-testid="vehicle-state-odometer">
                  {state.odometer_km != null ? `${state.odometer_km.toLocaleString("cs-CZ")} km` : "—"}
                </p>
                {state.odometer_km == null ? (
                  <p className="text-xs text-[#A1A1AA] mt-1">
                    K tomuto datu není zaznamenán žádný odečet tachometru.
                  </p>
                ) : (
                  <p className="text-xs text-[#52525B] mt-1">
                    {state.odometer_is_estimate
                      ? `Odhad: poslední odečet ${state.odometer_source_label?.toLowerCase()} + ${state.odometer_gps_delta_km} km podle GPS`
                      : `Odečet — ${state.odometer_source_label}`}
                    {state.odometer_source === "can" && " (přímo z vozidla)"}
                    {state.odometer_recorded_at &&
                      ` (${new Date(state.odometer_recorded_at).toLocaleDateString("cs-CZ")})`}
                  </p>
                )}
              </div>

              <div className="border border-[#E4E4E7] rounded-md p-4">
                <p className="text-sm text-[#52525B] flex items-center gap-1">
                  <GasPump size={16} weight="duotone" />Palivo k {new Date(at).toLocaleDateString("cs-CZ")}
                </p>
                <p className="text-3xl font-bold text-[#18181B]" data-testid="vehicle-state-fuel">
                  {state.fuel_level_percent != null
                    ? `${state.fuel_level_percent} %`
                    : state.fuel_level_liters != null
                      ? `${state.fuel_level_liters} l`
                      : "—"}
                </p>
                {state.fuel_level_percent != null && state.fuel_level_liters != null && (
                  <p className="text-sm text-[#52525B]">{state.fuel_level_liters} l</p>
                )}
                <p className="text-xs text-[#52525B] mt-1">
                  {state.fuel_source_label
                    ? `Zdroj: ${state.fuel_source_label}${state.fuel_recorded_at ? ` (${new Date(state.fuel_recorded_at).toLocaleString("cs-CZ")})` : ""}`
                    : "Bez údaje o stavu paliva."}
                </p>
                {state.last_refuel && (
                  <p className="text-xs text-[#52525B] mt-2">
                    Poslední tankování {new Date(state.last_refuel.date).toLocaleDateString("cs-CZ")}
                    {state.last_refuel.liters ? ` · ${state.last_refuel.liters} l` : ""}
                    {state.last_refuel.total_price ? ` · ${state.last_refuel.total_price} Kč` : ""}
                  </p>
                )}
              </div>
            </div>
          )}

          {daily.length > 0 && (
            <>
              <div className="border border-[#E4E4E7] rounded-md p-4">
                <h4 className="font-semibold text-[#18181B] mb-3 text-sm">Vývoj tachometru a paliva</h4>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={daily} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E4E4E7" />
                      <XAxis dataKey="date" tick={tick} tickFormatter={(v) => v.slice(5)} />
                      <YAxis yAxisId="km" tick={tick} domain={["auto", "auto"]} width={60} />
                      <YAxis yAxisId="fuel" orientation="right" tick={tick} domain={[0, 100]} width={40} />
                      <Tooltip
                        formatter={(value, name) =>
                          name === "Palivo" ? [`${value} %`, name] : [`${value?.toLocaleString("cs-CZ")} km`, name]}
                        labelFormatter={(l) => `Datum: ${l}`}
                      />
                      <Line yAxisId="km" type="monotone" dataKey="odometer_km" name="Tachometr"
                            stroke="#002FA7" strokeWidth={2} dot={false} connectNulls />
                      <Line yAxisId="fuel" type="monotone" dataKey="fuel_level_percent" name="Palivo"
                            stroke="#16A34A" strokeWidth={2} dot={false} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="border border-[#E4E4E7] rounded-md overflow-hidden">
                <div className="overflow-x-auto max-h-64">
                  <table className="data-table w-full">
                    <thead>
                      <tr><th>Datum</th><th>Tachometr</th><th>Palivo</th><th>Zdroje</th></tr>
                    </thead>
                    <tbody>
                      {[...daily].reverse().map((row) => (
                        <tr key={row.date}>
                          <td>{new Date(row.date).toLocaleDateString("cs-CZ")}</td>
                          <td>
                            {row.odometer_km != null ? `${row.odometer_km.toLocaleString("cs-CZ")} km` : "—"}
                            {row.odometer_is_estimate && (
                              <span className="ml-1 text-[10px] text-[#A1A1AA]">odhad</span>
                            )}
                          </td>
                          <td>{row.fuel_level_percent != null ? `${row.fuel_level_percent} %` : "—"}</td>
                          <td>
                            <span className="flex flex-wrap gap-1">
                              {row.sources.map((src) => (
                                <span key={src}
                                      className={`text-[10px] px-1.5 py-0.5 rounded ${SOURCE_STYLES[src] || "bg-zinc-100 text-zinc-700"}`}>
                                  {src}
                                </span>
                              ))}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {history && daily.length === 0 && !loading && (
            <p className="text-sm text-[#52525B] flex items-center gap-2">
              <Info size={16} />Ve zvoleném období nejsou žádné záznamy o tachometru ani palivu.
            </p>
          )}

          {history?.downsampled && (
            <p className="text-xs text-[#A1A1AA]">
              Zobrazen výběr z {history.total_readings} záznamů; uložená data zůstávají kompletní.
            </p>
          )}

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Zavřít</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
