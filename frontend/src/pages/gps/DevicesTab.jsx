import { Cpu, Plus, Trash, WifiHigh, WifiSlash, TestTube } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";

export function DevicesTab({ devices, vehicles, tcpStatus, testing, showDeviceModal, setShowDeviceModal, deviceForm, setDeviceForm, handleAddDevice, handleDeleteDevice, handleTestDevice }) {
  return (
    <div className="space-y-6">
      {/* TCP Server Status */}
      {tcpStatus && (
        <div className="bg-white border border-[#E4E4E7] rounded-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-[#18181B] flex items-center gap-2">
              <Cpu size={20} className="text-[#002FA7]" />
              Teltonika TCP Server
            </h3>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${tcpStatus.running ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {tcpStatus.running ? <WifiHigh size={16} /> : <WifiSlash size={16} />}
              {tcpStatus.running ? "Aktivní" : "Neaktivní"}
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div><p className="text-[#52525B]">Adresa</p><p className="font-medium font-mono text-[#18181B]">{tcpStatus.host}:{tcpStatus.port}</p></div>
            <div><p className="text-[#52525B]">Aktivní spojení</p><p className="font-medium text-[#18181B]">{tcpStatus.active_connections}</p></div>
            <div><p className="text-[#52525B]">Celkem záznamů</p><p className="font-medium text-[#18181B]">{tcpStatus.total_records_received}</p></div>
            <div><p className="text-[#52525B]">Protokol</p><p className="font-medium text-[#18181B]">Codec 8 / 8 Extended</p></div>
          </div>
          <div className="mt-4 p-3 bg-[#F4F4F5] rounded-md text-xs text-[#52525B]">
            Nastavte v Teltonika Configuratoru: Server IP = <span className="font-mono font-medium text-[#18181B]">vaše_veřejná_IP</span>, Port = <span className="font-mono font-medium text-[#18181B]">{tcpStatus.port}</span>, Protokol = <span className="font-mono font-medium text-[#18181B]">TCP</span>, Codec = <span className="font-mono font-medium text-[#18181B]">Codec 8 Extended</span>
          </div>
        </div>
      )}

      {/* Device List */}
      <div>
        <h3 className="font-semibold text-[#18181B] mb-4">Registrovaná zařízení ({devices.length})</h3>
        {devices.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {devices.map(device => (
              <div key={device.device_id} className="bg-white border border-[#E4E4E7] rounded-md p-5" data-testid={`device-${device.device_id}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Cpu size={20} className="text-[#002FA7]" />
                    <span className="font-semibold text-[#18181B]">{device.name}</span>
                  </div>
                  <div className={`w-2.5 h-2.5 rounded-full ${device.status === "online" ? "bg-[#16A34A] animate-pulse" : "bg-[#A1A1AA]"}`} />
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-[#52525B]">IMEI</span><span className="font-mono text-[#18181B]">{device.imei}</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Vozidlo</span><span className="text-[#18181B]">{device.vehicle_info || "-"}</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Stav</span><span className={device.status === "online" ? "text-green-600 font-medium" : "text-[#A1A1AA]"}>{device.status === "online" ? "Online" : "Offline"}</span></div>
                  <div className="flex justify-between"><span className="text-[#52525B]">Poslední spojení</span><span className="text-[#18181B]">{device.last_seen ? new Date(device.last_seen).toLocaleString("cs-CZ") : "-"}</span></div>
                </div>
                <div className="flex gap-2 mt-4 pt-3 border-t border-[#E4E4E7]">
                  <Button variant="outline" size="sm" onClick={() => handleTestDevice(device)} disabled={testing} className="flex-1" data-testid={`test-device-${device.device_id}`}>
                    <TestTube size={16} className="mr-1" />{testing ? "..." : "Test"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleDeleteDevice(device.device_id)} className="text-[#991B1B] hover:bg-red-50" data-testid={`delete-device-${device.device_id}`}>
                    <Trash size={16} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white border border-[#E4E4E7] rounded-md p-12 text-center">
            <Cpu size={48} weight="duotone" className="mx-auto text-[#A1A1AA] mb-4" />
            <h3 className="font-semibold text-[#18181B] mb-2">Žádné trackery</h3>
            <p className="text-[#52525B] mb-4">Registrujte GPS tracker a přiřaďte ho k vozidlu</p>
            <Button onClick={() => setShowDeviceModal(true)} className="bg-[#002FA7] hover:bg-[#002480]">
              <Plus size={20} className="mr-2" />Přidat tracker
            </Button>
          </div>
        )}
      </div>

      {/* Add Device Modal */}
      <Dialog open={showDeviceModal} onOpenChange={setShowDeviceModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="font-['Manrope']">Registrace GPS trackeru</DialogTitle></DialogHeader>
          <form onSubmit={handleAddDevice} className="space-y-4">
            <div>
              <Label htmlFor="imei">IMEI číslo *</Label>
              <Input id="imei" value={deviceForm.imei} onChange={(e) => setDeviceForm({ ...deviceForm, imei: e.target.value })} placeholder="352625090000001" required className="font-mono" data-testid="device-imei-input" />
              <p className="text-xs text-[#A1A1AA] mt-1">15místný kód na štítku trackeru</p>
            </div>
            <div>
              <Label>Vozidlo *</Label>
              <Select value={deviceForm.vehicle_id} onValueChange={(v) => setDeviceForm({ ...deviceForm, vehicle_id: v })}>
                <SelectTrigger data-testid="device-vehicle-select"><SelectValue placeholder="Vyberte vozidlo" /></SelectTrigger>
                <SelectContent>
                  {vehicles.map(v => <SelectItem key={v.vehicle_id} value={v.vehicle_id}>{v.brand} {v.model} ({v.registration_plate})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="device-name">Název (volitelné)</Label>
              <Input id="device-name" value={deviceForm.name} onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })} placeholder="FMB003 - vůz 1" data-testid="device-name-input" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowDeviceModal(false)}>Zrušit</Button>
              <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" disabled={!deviceForm.imei || !deviceForm.vehicle_id} data-testid="device-submit-btn">Registrovat</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
