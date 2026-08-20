import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";

export function VehicleFormModal({ open, onOpenChange, formData, setFormData, instructors, isEditing, onSubmit }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-['Manrope']">
            {isEditing ? "Upravit vozidlo" : "Nové vozidlo"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="brand">Značka *</Label>
              <Input
                id="brand"
                value={formData.brand}
                onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                required
                data-testid="vehicle-brand-input"
              />
            </div>
            <div>
              <Label htmlFor="model">Model *</Label>
              <Input
                id="model"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                required
                data-testid="vehicle-model-input"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="registration_plate">SPZ *</Label>
            <Input
              id="registration_plate"
              value={formData.registration_plate}
              onChange={(e) => setFormData({ ...formData, registration_plate: e.target.value.toUpperCase() })}
              required
              data-testid="vehicle-plate-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="year">Rok výroby *</Label>
              <Input
                id="year"
                type="number"
                min="1990"
                max={new Date().getFullYear() + 1}
                value={formData.year}
                onChange={(e) => setFormData({ ...formData, year: parseInt(e.target.value) })}
                required
                data-testid="vehicle-year-input"
              />
            </div>
            <div>
              <Label htmlFor="odometer">Tachometr (km)</Label>
              <Input
                id="odometer"
                type="number"
                min="0"
                value={formData.odometer}
                onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })}
                data-testid="vehicle-odometer-input"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="vin">VIN</Label>
            <Input
              id="vin"
              value={formData.vin}
              onChange={(e) => setFormData({ ...formData, vin: e.target.value.toUpperCase() })}
              data-testid="vehicle-vin-input"
            />
          </div>

          <div>
            <Label htmlFor="fuel_type">Typ paliva</Label>
            <Select value={formData.fuel_type} onValueChange={(value) => setFormData({ ...formData, fuel_type: value })}>
              <SelectTrigger data-testid="vehicle-fuel-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="benzín">Benzín</SelectItem>
                <SelectItem value="nafta">Nafta</SelectItem>
                <SelectItem value="LPG">LPG</SelectItem>
                <SelectItem value="elektro">Elektro</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="instructor">Přiřazený instruktor</Label>
            <Select
              value={formData.assigned_instructor_id || "none"}
              onValueChange={(value) => setFormData({ ...formData, assigned_instructor_id: value === "none" ? "" : value })}
            >
              <SelectTrigger data-testid="vehicle-instructor-select">
                <SelectValue placeholder="Vyberte instruktora" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Bez instruktora</SelectItem>
                {instructors.map((instructor) => (
                  <SelectItem key={instructor.instructor_id} value={instructor.instructor_id}>
                    {instructor.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="reservation_alias">Název v kalendáři (ICS)</Label>
            <Input
              id="reservation_alias"
              value={formData.reservation_alias || ""}
              onChange={(e) => setFormData({ ...formData, reservation_alias: e.target.value })}
              placeholder="Např. Černý Golf VII"
              data-testid="vehicle-alias-input"
            />
            <p className="text-xs text-[#A1A1AA] mt-1">Přesný název vozidla v rezervačním systému / kalendáři – slouží k napárování jízd a GPS.</p>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Zrušit
            </Button>
            <Button type="submit" className="bg-[#002FA7] hover:bg-[#002480]" data-testid="vehicle-submit-btn">
              {isEditing ? "Uložit" : "Přidat"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
