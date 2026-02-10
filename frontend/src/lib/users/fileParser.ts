/* eslint-disable @typescript-eslint/no-explicit-any */
import Papa from "papaparse";
import * as XLSX from "xlsx";

export type ParsedRow = { name: string; email: string; role?: string; team?: string, code?:string, type?:string };

export function parseCsvFile(file: File): Promise<ParsedRow[]> {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results: { data: any[]; }) => {
        const rows = (results.data as any[]).map(r => ({
          name: (r.name || r.fullname || r.Name || "").trim(),
          email: (r.email || r.Email || "").trim(),
          role: (r.role || r.Role || "Member").trim(),
          team: (r.team || r.Team || "Research").trim(),
          code: (r.code || r.Code || "2310000").trim(),
          type: (r.type || r.Type || "CLC").trim(),
        })).filter(r => r.name && r.email);
        resolve(rows);
      },
      error: (err: any) => reject(err),
    });
  });
}

export function parseXlsxFile(file: File): Promise<ParsedRow[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = e.target?.result;
        const workbook = XLSX.read(data, { type: "array" });
        const wsName = workbook.SheetNames[0];
        const ws = workbook.Sheets[wsName];
        const json = XLSX.utils.sheet_to_json(ws, { defval: "" }) as any[];
        const rows = json.map(r => ({
          name: (r.name || r.fullname || r.Name || "").trim(),
          email: (r.email || r.Email || "").trim(),
          role: (r.role || r.Role || "Member").trim(),
          team: (r.team || r.Team || "Research").trim(),
        })).filter(r => r.name && r.email);
        resolve(rows);
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = (err) => reject(err);
    reader.readAsArrayBuffer(file);
  });
}

export async function parseFile(file: File) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".csv")) return parseCsvFile(file);
  if (name.endsWith(".xlsx") || name.endsWith(".xls")) return parseXlsxFile(file);
  throw new Error("Unsupported file type. Use .csv or .xlsx/.xls");
}
