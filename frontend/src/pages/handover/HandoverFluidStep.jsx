import { Check, Warning } from "@phosphor-icons/react";
import { Checkbox } from "../../components/ui/checkbox";

const FLUID_CHECKS = [
  { id: "engine_oil", label: "Motorový olej", description: "Zkontrolován a doplněn" },
  { id: "coolant", label: "Chladicí kapalina", description: "Zkontrolována a doplněna" },
  { id: "brake_fluid", label: "Brzdová kapalina", description: "Zkontrolována a doplněna" },
  { id: "windshield_washer", label: "Kapalina ostřikovačů", description: "Zkontrolována a doplněna" },
  { id: "other_fluids", label: "Ostatní provozní kapaliny", description: "Zkontrolovány (servo, převodovka)" }
];

export { FLUID_CHECKS };

export function HandoverFluidStep({ fluidChecks, setFluidChecks }) {
  const allChecked = FLUID_CHECKS.every((f) => fluidChecks[f.id] === true);

  return (
    <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in" data-testid="handover-fluid-step">
      <h2 className="text-lg font-bold text-[#18181B]">Kontrola provozních kapalin</h2>
      <p className="text-sm text-[#52525B]">
        Potvrďte, že jste zkontrolovali a případně doplnili všechny provozní kapaliny:
      </p>

      <div className="space-y-3">
        {FLUID_CHECKS.map((fluid) => (
          <label
            key={fluid.id}
            className={`flex items-start gap-3 p-4 border rounded-lg cursor-pointer transition-all ${
              fluidChecks[fluid.id]
                ? "border-[#002FA7] bg-[#002FA7]/5"
                : "border-[#E4E4E7] hover:border-[#A1A1AA]"
            }`}
          >
            <Checkbox
              checked={fluidChecks[fluid.id]}
              onCheckedChange={(checked) => setFluidChecks({ ...fluidChecks, [fluid.id]: checked })}
              className="mt-0.5"
            />
            <div className="flex-1">
              <p className="font-medium text-[#18181B]">{fluid.label}</p>
              <p className="text-sm text-[#52525B]">{fluid.description}</p>
            </div>
            {fluidChecks[fluid.id] && <Check size={20} className="text-[#16A34A]" />}
          </label>
        ))}
      </div>

      {!allChecked && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <Warning size={20} className="text-amber-600" />
          <p className="text-sm text-amber-800">Všechny položky musí být zaškrtnuté</p>
        </div>
      )}
    </div>
  );
}
