import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { API } from "../App";
import { MapPin, Broadcast, Path, Cpu, Plus } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { LiveMapTab } from "./gps/LiveMapTab";
import { TripHistoryTab } from "./gps/TripHistoryTab";
import { DevicesTab } from "./gps/DevicesTab";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

export default function GPSTracking() {
  const [tab, setTab] = useState("live");
  const [trips, setTrips] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState("");
  const [selectedTrip, setSelectedTrip] = useState(null);

  const [livePositions, setLivePositions] = useState([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef(null);

  const [devices, setDevices] = useState([]);
  const [tcpStatus, setTcpStatus] = useState(null);
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [deviceForm, setDeviceForm] = useState({ imei: "", vehicle_id: "", name: "" });
  const [testing, setTesting] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const params = selectedVehicle && selectedVehicle !== "all" ? `?vehicle_id=${selectedVehicle}` : "";
      const [tripsRes, vehiclesRes] = await Promise.all([
        axios.get(`${API}/gps/trips${params}`, { withCredentials: true }),
        axios.get(`${API}/vehicles`, { withCredentials: true })
      ]);
      setTrips(tripsRes.data);
      setVehicles(vehiclesRes.data);
    } catch { toast.error("Nepodařilo se načíst GPS data"); }
    finally { setLoading(false); }
  }, [selectedVehicle]);

  const fetchDevices = useCallback(async () => {
    try {
      const [devRes, statusRes] = await Promise.all([
        axios.get(`${API}/gps/devices`, { withCredentials: true }),
        axios.get(`${API}/gps/tcp-status`, { withCredentials: true })
      ]);
      setDevices(devRes.data);
      setTcpStatus(statusRes.data);
    } catch { toast.error("Nepodařilo se načíst zařízení"); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { if (tab === "devices") fetchDevices(); }, [tab, fetchDevices]);

  const fetchLivePositions = useCallback(async () => {
    setLiveLoading(true);
    try {
      const res = await axios.get(`${API}/gps/live-positions`, { withCredentials: true });
      setLivePositions(res.data);
    } catch { toast.error("Nepodařilo se načíst live pozice"); }
    finally { setLiveLoading(false); }
  }, []);

  const simulateAndFetch = useCallback(async () => {
    try {
      await axios.post(`${API}/gps/simulate-live`, {}, { withCredentials: true });
      await fetchLivePositions();
    } catch { toast.error("Simulace selhala"); }
  }, [fetchLivePositions]);

  useEffect(() => { if (tab === "live") fetchLivePositions(); }, [tab, fetchLivePositions]);

  useEffect(() => {
    if (autoRefresh && tab === "live") {
      intervalRef.current = setInterval(simulateAndFetch, 5000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, tab, simulateAndFetch]);

  const handleImportMock = async (vehicleId) => {
    if (!vehicleId) { toast.error("Vyberte vozidlo"); return; }
    setImporting(true);
    try {
      await axios.post(`${API}/gps/import-mock?vehicle_id=${vehicleId}`, {}, { withCredentials: true });
      toast.success("GPS data importována");
      fetchData();
    } catch { toast.error("Nepodařilo se importovat data"); }
    finally { setImporting(false); }
  };

  const handleSyncToLogbook = async (tripId) => {
    try {
      await axios.post(`${API}/gps/trips/${tripId}/sync-to-logbook`, {}, { withCredentials: true });
      toast.success("Synchronizováno do knihy jízd");
      fetchData();
    } catch { toast.error("Nepodařilo se synchronizovat"); }
  };

  const handleAddDevice = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/gps/devices`, deviceForm, { withCredentials: true });
      toast.success("Zařízení registrováno");
      setShowDeviceModal(false);
      setDeviceForm({ imei: "", vehicle_id: "", name: "" });
      fetchDevices();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Nepodařilo se registrovat");
    }
  };

  const handleDeleteDevice = async (deviceId) => {
    try {
      await axios.delete(`${API}/gps/devices/${deviceId}`, { withCredentials: true });
      toast.success("Zařízení odstraněno");
      fetchDevices();
    } catch { toast.error("Nepodařilo se odstranit"); }
  };

  const handleTestDevice = async (device) => {
    setTesting(true);
    try {
      const res = await axios.post(`${API}/gps/test-teltonika?imei=${device.imei}&lat=50.0755&lng=14.4378&speed=45`, {}, { withCredentials: true });
      if (res.data.success) {
        toast.success(`Test OK: ${res.data.records_acked} záznam(y) přijaty`);
        fetchDevices();
        fetchLivePositions();
      } else {
        toast.error(`Test selhal: ${res.data.error}`);
      }
    } catch { toast.error("Nepodařilo se provést test"); }
    finally { setTesting(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="loading-spinner"></div></div>;

  return (
    <div className="space-y-6" data-testid="gps-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-['Manrope'] text-2xl lg:text-3xl font-bold text-[#18181B] tracking-tight">GPS sledování</h1>
          <p className="text-[#52525B] mt-1">Live mapa, historie tras a správa trackerů</p>
        </div>
        {tab === "devices" && (
          <Button onClick={() => setShowDeviceModal(true)} className="bg-[#002FA7] hover:bg-[#002480]" data-testid="add-device-btn">
            <Plus size={20} className="mr-2" />Přidat tracker
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-[#F4F4F5] p-1 rounded-lg w-fit">
        <button onClick={() => setTab("live")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "live" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-live">
          <Broadcast size={18} />Live mapa
        </button>
        <button onClick={() => setTab("history")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "history" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-history">
          <Path size={18} />Historie tras
        </button>
        <button onClick={() => setTab("devices")} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === "devices" ? "bg-white text-[#18181B] shadow-sm" : "text-[#52525B] hover:text-[#18181B]"}`} data-testid="tab-devices">
          <Cpu size={18} />Trackery
        </button>
      </div>

      {tab === "live" && (
        <LiveMapTab
          livePositions={livePositions}
          liveLoading={liveLoading}
          autoRefresh={autoRefresh}
          setAutoRefresh={setAutoRefresh}
          simulateAndFetch={simulateAndFetch}
        />
      )}

      {tab === "history" && (
        <TripHistoryTab
          trips={trips}
          vehicles={vehicles}
          selectedVehicle={selectedVehicle}
          setSelectedVehicle={setSelectedVehicle}
          selectedTrip={selectedTrip}
          setSelectedTrip={setSelectedTrip}
          importing={importing}
          handleImportMock={handleImportMock}
          handleSyncToLogbook={handleSyncToLogbook}
        />
      )}

      {tab === "devices" && (
        <DevicesTab
          devices={devices}
          vehicles={vehicles}
          tcpStatus={tcpStatus}
          testing={testing}
          showDeviceModal={showDeviceModal}
          setShowDeviceModal={setShowDeviceModal}
          deviceForm={deviceForm}
          setDeviceForm={setDeviceForm}
          handleAddDevice={handleAddDevice}
          handleDeleteDevice={handleDeleteDevice}
          handleTestDevice={handleTestDevice}
        />
      )}
    </div>
  );
}
