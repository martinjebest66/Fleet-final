import { useState } from "react";
import axios from "axios";
import { API, errorMessage } from "@/lib/api";
import { Camera, FilePdf, Image as ImageIcon, Trash, Paperclip, X } from "@phosphor-icons/react";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Input } from "../../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { toast } from "sonner";

export const DOC_TYPES = ["faktura", "STK protokol", "servisní kniha", "účtenka", "foto", "jiné"];

const formatSize = (bytes) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} kB`;

/**
 * Photographed documents attached to one maintenance record — invoices, the
 * STK protocol, service-book pages.
 *
 * On a phone the file input opens the camera directly (`capture`), so the
 * document can be photographed at the garage counter instead of being
 * uploaded later from a desktop.
 */
export function MaintenanceDocuments({ item, onChanged, compact = false }) {
  const [uploading, setUploading] = useState(false);
  const [docType, setDocType] = useState("faktura");
  const [label, setLabel] = useState("");
  const [preview, setPreview] = useState(null);
  const documents = item.documents || [];

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("doc_type", docType);
      if (label.trim()) fd.append("label", label.trim());
      await axios.post(`${API}/maintenance/${item.maintenance_id}/documents`, fd, {
        withCredentials: true,
        // Phone photos are several MB over a mobile connection.
        timeout: 120000,
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Doklad uložen");
      setLabel("");
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Doklad se nepodařilo nahrát"));
    } finally {
      setUploading(false);
    }
  };

  const remove = async (documentId) => {
    try {
      await axios.delete(`${API}/maintenance/documents/${documentId}`, { withCredentials: true });
      toast.success("Doklad smazán");
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, "Doklad se nepodařilo smazat"));
    }
  };

  const isPdf = (doc) => doc.content_type === "application/pdf";

  return (
    <div className="space-y-3" data-testid={`maintenance-documents-${item.maintenance_id}`}>
      {!compact && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>Typ dokladu</Label>
            <Select value={docType} onValueChange={setDocType}>
              <SelectTrigger data-testid="document-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DOC_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Popis (volitelné)</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)}
                   placeholder="např. Faktura 2026/114" data-testid="document-label-input" />
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm" disabled={uploading}>
          <label className="cursor-pointer">
            <Camera size={16} className="mr-1" />
            {uploading ? "Nahrávám…" : "Vyfotit doklad"}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              disabled={uploading}
              onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }}
              data-testid="document-camera-input"
            />
          </label>
        </Button>
        <Button asChild variant="outline" size="sm" disabled={uploading}>
          <label className="cursor-pointer">
            <Paperclip size={16} className="mr-1" />Nahrát soubor
            <input
              type="file"
              accept="image/*,application/pdf"
              className="hidden"
              disabled={uploading}
              onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }}
              data-testid="document-file-input"
            />
          </label>
        </Button>
      </div>

      {documents.length > 0 ? (
        <ul className="space-y-2">
          {documents.map((doc) => (
            <li key={doc.document_id}
                className="flex items-center gap-3 border border-[#E4E4E7] rounded-md p-2">
              <button
                type="button"
                onClick={() => (isPdf(doc) ? window.open(doc.url, "_blank", "noopener") : setPreview(doc))}
                className="shrink-0 w-12 h-12 rounded bg-[#F4F4F5] flex items-center justify-center overflow-hidden"
                title="Otevřít doklad"
              >
                {isPdf(doc)
                  ? <FilePdf size={22} weight="duotone" className="text-red-600" />
                  : <img src={doc.url} alt={doc.label || doc.doc_type}
                         className="w-full h-full object-cover" loading="lazy" />}
              </button>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#18181B] truncate">
                  {doc.label || doc.doc_type}
                </p>
                <p className="text-xs text-[#A1A1AA] truncate">
                  {doc.doc_type} · {formatSize(doc.size_bytes)} ·{" "}
                  {new Date(doc.uploaded_at).toLocaleDateString("cs-CZ")}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => remove(doc.document_id)}
                      className="text-red-600 hover:bg-red-50 shrink-0"
                      data-testid={`delete-document-${doc.document_id}`}>
                <Trash size={16} />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-[#A1A1AA] flex items-center gap-1">
          <ImageIcon size={14} />Zatím žádné doklady
        </p>
      )}

      <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between gap-4">
              <span className="truncate">{preview?.label || preview?.doc_type}</span>
              <button type="button" onClick={() => setPreview(null)} aria-label="Zavřít">
                <X size={18} />
              </button>
            </DialogTitle>
          </DialogHeader>
          {preview && (
            <div className="space-y-2">
              <img src={preview.url} alt={preview.label || preview.doc_type}
                   className="w-full max-h-[70vh] object-contain rounded" />
              <p className="text-xs text-[#52525B]">
                {preview.doc_type} · {formatSize(preview.size_bytes)} · nahráno{" "}
                {new Date(preview.uploaded_at).toLocaleString("cs-CZ")}
                {preview.uploaded_by ? ` · ${preview.uploaded_by}` : ""}
              </p>
              <a href={preview.url} target="_blank" rel="noopener noreferrer"
                 className="text-sm text-[#002FA7] underline">Otevřít v novém okně</a>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
