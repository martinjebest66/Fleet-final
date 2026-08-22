import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { API } from "../App";
import { errorMessage } from "@/lib/api";
import { Broadcast, Path, Cpu, Plus } from "@phosphor-icons/react";
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
  const [selectedRoute, setSelectedRoute] = useState({ points: [], loading: false });
  const [allowMockData, setAllowMockData] = useState(false);

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
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se načíst GPS data")); }
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
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se načíst zařízení")); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { if (tab === "devices") fetchDevices(); }, [tab, fetchDevices]);

  // The demo-data generators are disabled in production, so do not offer a
  // button the backend will refuse.
  useEffect(() => {
    let active = true;
    axios
      .get(`${API}/config`, { withCredentials: true })
      .then((res) => { if (active) setAllowMockData(Boolean(res.data.allow_mock_data)); })
      .catch(() => { if (active) setAllowMockData(false); });
    return () => { active = false; };
  }, []);

  // The trip list no longer carries route points — a long history would ship
  // megabytes of coordinates the list never draws. The route of the selected
  // trip is fetched on demand and down-sampled server-side for the map; the
  // stored GPS history itself is never trimmed.
  useEffect(() => {
    if (!selectedTrip?.trip_id) {
      setSelectedRoute({ points: [], loading: false });
      return undefined;
    }
    const controller = new AbortController();
    setSelectedRoute({ points: [], loading: true });
    axios
      .get(`${API}/gps/trips/${selectedTrip.trip_id}/route`, {
        withCredentials: true,
        signal: controller.signal,
      })
      .then((res) => setSelectedRoute({
        points: res.data.points || [],
        stateStart: res.data.state_start,
        stateEnd: res.data.state_end,
        loading: false,
      }))
      .catch((err) => {
        if (axios.isCancel(err) || err.name === "CanceledError") return;
        setSelectedRoute({ points: [], loading: false });
        toast.error(errorMessage(err, "Nepodařilo se načíst trasu jízdy"));
      });
    return () => controller.abort();
  }, [selectedTrip?.trip_id]);

  const fetchLivePositions = useCallback(async () => {
    setLiveLoading(true);
    try {
      const res = await axios.get(`${API}/gps/live-positions`, { withCredentials: true });
      setLivePositions(res.data);
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se načíst live pozice")); }
    finally { setLiveLoading(false); }
  }, []);

  const simulateAndFetch = useCallback(async () => {
    try {
      await axios.post(`${API}/gps/simulate-live`, {}, { withCredentials: true });
      await fetchLivePositions();
    } catch (err) { toast.error(errorMessage(err, "Simulace selhala")); }
  }, [fetchLivePositions]);

  useEffect(() => { if (tab === "live") fetchLivePositions(); }, [tab, fetchLivePositions]);

  // Auto-refresh reloads the real tracker positions. It used to call the mock
  // generator instead, which both wrote fabricated positions into the database
  // every five seconds and — once the generator was disabled outside
  // development — left the live map permanently stale.
  useEffect(() => {
    if (autoRefresh && tab === "live") {
      intervalRef.current = setInterval(fetchLivePositions, 15000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, tab, fetchLivePositions]);

  const handleImportMock = async (vehicleId) => {
    if (!vehicleId) { toast.error("Vyberte vozidlo"); return; }
    setImporting(true);
    try {
      await axios.post(`${API}/gps/import-mock?vehicle_id=${vehicleId}`, {}, { withCredentials: true });
      toast.success("GPS data importována");
      fetchData();
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se importovat data")); }
    finally { setImporting(false); }
  };

  const handleSyncToLogbook = async (tripId) => {
    try {
      await axios.post(`${API}/gps/trips/${tripId}/sync-to-logbook`, {}, { withCredentials: true });
      toast.success("Synchronizováno do knihy jízd");
      fetchData();
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se synchronizovat")); }
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
      toast.error(errorMessage(err, "Nepodařilo se registrovat"));
    }
  };

  const handleDeleteDevice = async (deviceId) => {
    try {
      await axios.delete(`${API}/gps/devices/${deviceId}`, { withCredentials: true });
      toast.success("Zařízení odstraněno");
      fetchDevices();
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se odstranit")); }
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
    } catch (err) { toast.error(errorMessage(err, "Nepodařilo se provést test")); }
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
          allowMockData={allowMockData}
          refresh={fetchLivePositions}
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
          selectedRoute={selectedRoute}
          allowMockData={allowMockData}
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
