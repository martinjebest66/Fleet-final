import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";

export function HandoverInfoStep({ formData, setFormData }) {
  return (
    <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in" data-testid="handover-info-step">
      <h2 className="text-lg font-bold text-[#18181B]">Základní údaje</h2>

      <div>
        <Label>Vaše jméno *</Label>
        <Input
          value={formData.handler_name}
          onChange={(e) => setFormData({ ...formData, handler_name: e.target.value })}
          placeholder="Jan Novák"
          className="mt-1"
          data-testid="handler-name-input"
        />
      </div>

      <div>
        <Label>Typ předávky *</Label>
        <Select
          value={formData.handler_type}
          onValueChange={(v) => setFormData({ ...formData, handler_type: v })}
        >
          <SelectTrigger className="mt-1" data-testid="handler-type-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="převzetí">Převzetí vozidla</SelectItem>
            <SelectItem value="předání">Předání vozidla</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label>Stav tachometru (km) *</Label>
        <Input
          type="number"
          min="0"
          value={formData.odometer}
          onChange={(e) => setFormData({ ...formData, odometer: parseInt(e.target.value) || 0 })}
          className="mt-1"
          data-testid="odometer-input"
        />
      </div>

      <div>
        <Label>Stav paliva (%)</Label>
        <div className="flex items-center gap-4 mt-1">
          <Input
            type="range"
            min="0"
            max="100"
            step="5"
            value={formData.fuel_level}
            onChange={(e) => setFormData({ ...formData, fuel_level: parseInt(e.target.value) })}
            className="flex-1"
            data-testid="fuel-level-input"
          />
          <span className="w-12 text-center font-bold">{formData.fuel_level}%</span>
        </div>
      </div>
    </div>
  );
}
