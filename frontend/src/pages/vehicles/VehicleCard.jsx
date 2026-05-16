import { Car, Pencil, Trash, QrCode, Handshake } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";

export function VehicleCard({ vehicle, getInstructorName, onEdit, onDelete, onQR }) {
  return (
    <div
      className="bg-white border border-[#E4E4E7] rounded-md p-6 card-hover"
      data-testid={`vehicle-card-${vehicle.vehicle_id}`}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#F4F4F5] rounded-md flex items-center justify-center">
            <Car size={24} weight="duotone" className="text-[#002FA7]" />
          </div>
          <div>
            <h3 className="font-semibold text-[#18181B]">{vehicle.brand} {vehicle.model}</h3>
            <p className="text-sm text-[#52525B]">{vehicle.registration_plate}</p>
          </div>
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-[#52525B]">Rok</span>
          <span className="font-medium text-[#18181B]">{vehicle.year}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[#52525B]">Tachometr</span>
          <span className="font-medium text-[#18181B]">{vehicle.odometer?.toLocaleString("cs-CZ")} km</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[#52525B]">Palivo</span>
          <span className="font-medium text-[#18181B]">{vehicle.fuel_type}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[#52525B]">Instruktor</span>
          <span className="font-medium text-[#18181B]">{getInstructorName(vehicle.assigned_instructor_id)}</span>
        </div>
      </div>

      <div className="flex gap-2 mt-4 pt-4 border-t border-[#E4E4E7]">
        <Button variant="outline" size="sm" onClick={() => onQR(vehicle, "fuel")} className="flex-1" data-testid={`qr-fuel-${vehicle.vehicle_id}`}>
          <QrCode size={16} className="mr-1" />
          Tankování
        </Button>
        <Button variant="outline" size="sm" onClick={() => onQR(vehicle, "damage")} className="flex-1" data-testid={`qr-damage-${vehicle.vehicle_id}`}>
          <QrCode size={16} className="mr-1" />
          Poškození
        </Button>
      </div>

      <div className="mt-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onQR(vehicle, "handover")}
          className="w-full bg-[#002FA7]/5 border-[#002FA7]/20 text-[#002FA7] hover:bg-[#002FA7]/10"
          data-testid={`qr-handover-${vehicle.vehicle_id}`}
        >
          <Handshake size={16} className="mr-1" />
          Předávka vozidla
        </Button>
      </div>

      <div className="flex gap-2 mt-2">
        <Button variant="outline" size="sm" onClick={() => onEdit(vehicle)} className="flex-1" data-testid={`edit-vehicle-${vehicle.vehicle_id}`}>
          <Pencil size={16} className="mr-1" />
          Upravit
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onDelete(vehicle)}
          className="text-[#991B1B] hover:bg-red-50"
          data-testid={`delete-vehicle-${vehicle.vehicle_id}`}
        >
          <Trash size={16} />
        </Button>
      </div>
    </div>
  );
}
