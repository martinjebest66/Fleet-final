import { useRef } from "react";
import { Camera, Check } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";

const PHOTO_STEPS = [
  { id: "front", label: "Přední strana", instruction: "Vyfoťte vozidlo zepředu (čelní pohled)" },
  { id: "rear", label: "Zadní strana", instruction: "Vyfoťte vozidlo zezadu" },
  { id: "left", label: "Levá strana", instruction: "Vyfoťte vozidlo z levé strany" },
  { id: "right", label: "Pravá strana", instruction: "Vyfoťte vozidlo z pravé strany" },
  { id: "interior", label: "Interiér", instruction: "Vyfoťte interiér vozidla (sedadla, přístrojovka)" },
  { id: "dashboard", label: "Palubní deska", instruction: "Vyfoťte palubní desku s ukazatelem paliva a tachometrem" }
];

export { PHOTO_STEPS };

export function HandoverPhotoStep({ photoIndex, photos, onPhotoCapture, onRetakePhoto, uploadingPhoto }) {
  const fileInputRef = useRef(null);
  const photoStep = PHOTO_STEPS[photoIndex];
  const currentPhoto = photos[photoStep.id];

  return (
    <div className="bg-white rounded-lg p-6 space-y-4 animate-fade-in" data-testid="handover-photo-step">
      <div className="text-center">
        <div className="inline-flex items-center gap-2 bg-[#F4F4F5] px-4 py-2 rounded-full mb-4">
          <Camera size={20} className="text-[#002FA7]" />
          <span className="font-semibold">Foto {photoIndex + 1} z 6</span>
        </div>
        <h2 className="text-lg font-bold text-[#18181B]">{photoStep.label}</h2>
        <p className="text-sm text-[#52525B] mt-1">{photoStep.instruction}</p>
      </div>

      {currentPhoto ? (
        <div className="relative">
          <img
            src={currentPhoto.photo_url}
            alt={photoStep.label}
            className="w-full h-64 object-cover rounded-lg"
          />
          <div className="absolute top-2 right-2 bg-green-500 text-white px-3 py-1 rounded-full text-sm font-medium flex items-center gap-1">
            <Check size={16} />
            Pořízeno
          </div>
          <Button
            variant="outline"
            onClick={() => onRetakePhoto(photoStep.id)}
            className="absolute bottom-2 right-2 bg-white"
          >
            <Camera size={16} className="mr-1" />
            Pořídit znovu
          </Button>
        </div>
      ) : (
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-[#E4E4E7] rounded-lg p-8 text-center cursor-pointer hover:border-[#002FA7] hover:bg-[#002FA7]/5 transition-all"
        >
          {uploadingPhoto ? (
            <div className="loading-spinner mx-auto"></div>
          ) : (
            <>
              <Camera size={48} className="mx-auto text-[#A1A1AA] mb-4" />
              <p className="text-[#52525B] mb-2">Klikněte pro pořízení fotografie</p>
              <p className="text-xs text-[#A1A1AA]">Nebo přetáhněte soubor</p>
            </>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={(e) => {
          onPhotoCapture(e, photoStep.id);
          if (fileInputRef.current) fileInputRef.current.value = "";
        }}
        className="hidden"
      />

      {/* Photo thumbnails progress */}
      <div className="flex gap-2 justify-center">
        {PHOTO_STEPS.map((step, idx) => (
          <div
            key={step.id}
            className={`w-10 h-10 rounded-lg overflow-hidden border-2 ${
              idx === photoIndex
                ? "border-[#002FA7]"
                : photos[step.id]
                  ? "border-green-500"
                  : "border-[#E4E4E7]"
            }`}
          >
            {photos[step.id] ? (
              <img src={photos[step.id].photo_url} alt={step.label} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full bg-[#F4F4F5] flex items-center justify-center">
                <span className="text-xs text-[#A1A1AA]">{idx + 1}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
