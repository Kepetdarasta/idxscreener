import { neon } from "@neondatabase/serverless";

// Pakai connection string role read-only (dashboard_ro), bukan kredensial ETL.
export const sql = neon(process.env.DATABASE_URL!);
