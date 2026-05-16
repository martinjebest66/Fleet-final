import { Handshake } from "@phosphor-icons/react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { QRCodeSVG } from "qrcode.react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const QR_TITLES = {
  fuel: "QR kód pro tankování",
  damage: "QR kód pro hlášení poškození",
  handover: "QR kód pro předávku vozidla"
};

const QR_DESCRIPTIONS = {
  fuel: "zaznamenání tankování",
  damage: "nahlášení poškození",
  handover: "předávací protokol"
};

function getQRUrl(vehicle, type) {
  let code;
  if (type === "fuel") code = vehicle.qr_code_fuel;
  else if (type === "damage") code = vehicle.qr_code_damage;
  else code = vehicle.qr_code_handover || `handover_${vehicle.vehicle_id}`;
  return `${BACKEND_URL}/${type}/${code}`;
}

export function VehicleQRModal({ open, onOpenChange, vehicle, qrType }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="font-['Manrope']">
            {QR_TITLES[qrType] || "QR kód"}
          </DialogTitle>
        </DialogHeader>
        {vehicle && (
          <div className="text-center">
            <p className="text-sm text-[#52525B] mb-4">
              {vehicle.brand} {vehicle.model} ({vehicle.registration_plate})
            </p>
            <div className="bg-white p-6 inline-block rounded-lg border border-[#E4E4E7]">
              <QRCodeSVG value={getQRUrl(vehicle, qrType)} size={200} level="H" />
            </div>
            <p className="text-xs text-[#52525B] mt-4">
              Naskenujte pro {QR_DESCRIPTIONS[qrType] || ""}
            </p>
            {qrType === "handover" && (
              <p className="text-xs text-[#002FA7] mt-2 font-medium">
                Obsahuje kontrolu kapalin a 6 povinných fotografií
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
