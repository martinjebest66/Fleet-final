import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { PHOTO_STEPS } from "./HandoverPhotoStep";

export function HandoverReviewStep({ formData, setFormData, photos, error }) {
  return (
    <div className="space-y-4 animate-fade-in" data-testid="handover-review-step">
      <div className="bg-white rounded-lg p-6">
        <h2 className="text-lg font-bold text-[#18181B] mb-4">Kontrola před odesláním</h2>

        <div className="space-y-3">
          <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
            <span className="text-[#52525B]">Jméno</span>
            <span className="font-medium">{formData.handler_name}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
            <span className="text-[#52525B]">Typ</span>
            <span className="font-medium capitalize">{formData.handler_type}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
            <span className="text-[#52525B]">Tachometr</span>
            <span className="font-medium">{formData.odometer.toLocaleString("cs-CZ")} km</span>
          </div>
          <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
            <span className="text-[#52525B]">Palivo</span>
            <span className="font-medium">{formData.fuel_level}%</span>
          </div>
          <div className="flex justify-between py-2 border-b border-[#E4E4E7]">
            <span className="text-[#52525B]">Kapaliny</span>
            <span className="font-medium text-green-600">Zkontrolovány</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-[#52525B]">Fotografie</span>
            <span className="font-medium text-green-600">6/6 pořízeno</span>
          </div>
        </div>
      </div>

      {/* Photo grid */}
      <div className="bg-white rounded-lg p-6">
        <h3 className="font-semibold text-[#18181B] mb-3">Pořízené fotografie</h3>
        <div className="grid grid-cols-3 gap-2">
          {PHOTO_STEPS.map((step) => (
            <div key={step.id} className="relative aspect-square">
              <img
                src={photos[step.id]?.photo_url}
                alt={step.label}
                className="w-full h-full object-cover rounded-lg"
              />
              <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs p-1 text-center rounded-b-lg">
                {step.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Notes */}
      <div className="bg-white rounded-lg p-6">
        <Label>Poznámky (volitelné)</Label>
        <Textarea
          value={formData.notes}
          onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
          placeholder="Další poznámky k předávce..."
          rows={3}
          className="mt-2"
          data-testid="handover-notes-input"
        />
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm" data-testid="handover-error">
          {error}
        </div>
      )}
    </div>
  );
}
