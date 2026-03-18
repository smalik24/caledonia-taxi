-- Caledonia Taxi - Supabase Database Schema
-- Run this in the Supabase SQL Editor

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- DRIVERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS drivers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    pin VARCHAR(6) NOT NULL,  -- Simple PIN auth for MVP
    status VARCHAR(20) DEFAULT 'offline' CHECK (status IN ('available', 'busy', 'offline')),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    last_location_update TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- BOOKINGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    pickup_address TEXT NOT NULL,
    pickup_lat DOUBLE PRECISION,
    pickup_lng DOUBLE PRECISION,
    dropoff_address TEXT NOT NULL,
    dropoff_lat DOUBLE PRECISION,
    dropoff_lng DOUBLE PRECISION,
    estimated_distance_km DOUBLE PRECISION,
    estimated_fare DECIMAL(10, 2),
    actual_fare DECIMAL(10, 2),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'dispatched', 'accepted', 'in_progress', 'completed', 'cancelled')),
    assigned_driver_id UUID REFERENCES drivers(id),
    source VARCHAR(20) DEFAULT 'web' CHECK (source IN ('web', 'phone', 'admin')),
    dispatch_attempts INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- DISPATCH LOG TABLE (tracks which drivers were offered a ride)
-- ============================================
CREATE TABLE IF NOT EXISTS dispatch_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID REFERENCES bookings(id) ON DELETE CASCADE,
    driver_id UUID REFERENCES drivers(id),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'timeout')),
    dispatched_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_bookings_driver ON bookings(assigned_driver_id);
CREATE INDEX idx_drivers_status ON drivers(status);
CREATE INDEX idx_dispatch_log_booking ON dispatch_log(booking_id);

-- ============================================
-- SEED DATA - 4 Drivers (including owner Saqib)
-- ============================================
INSERT INTO drivers (name, phone, pin, status, latitude, longitude) VALUES
    ('Saqib', '+12895551001', '1234', 'available', 43.2557, -79.8711),
    ('Driver 2', '+12895551002', '2345', 'available', 43.2500, -79.8650),
    ('Driver 3', '+12895551003', '3456', 'offline', 43.2600, -79.8800),
    ('Driver 4', '+12895551004', '4567', 'offline', 43.2450, -79.8750)
ON CONFLICT (phone) DO NOTHING;

-- ============================================
-- ROW LEVEL SECURITY (basic, expand later)
-- ============================================
ALTER TABLE drivers ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE dispatch_log ENABLE ROW LEVEL SECURITY;

-- Allow all operations for authenticated users (MVP - relax later)
CREATE POLICY "Allow all for anon" ON drivers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON bookings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON dispatch_log FOR ALL USING (true) WITH CHECK (true);

-- ============================================
-- REALTIME (enable for live updates)
-- ============================================
-- In Supabase dashboard, enable Realtime for: bookings, drivers, dispatch_log

-- =============================================
-- MIGRATION: 2026-03-18 full platform redesign
-- =============================================
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'standard';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stops JSONB DEFAULT '[]';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS fare_breakdown JSONB;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS oasr_source BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

ALTER TABLE drivers ADD COLUMN IF NOT EXISTS vehicle TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS plate TEXT DEFAULT '';
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS inactive BOOLEAN DEFAULT FALSE;

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
  CHECK (status IN ('pending','dispatched','accepted','in_progress','completed','cancelled','scheduled','dispatch_failed','needs_review'));

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_source_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_source_check
  CHECK (source IN ('web','phone','admin','voice_ai','oasr'));

-- =============================================
-- MIGRATION: 2026-03-18 production hardening
-- =============================================

-- Driver location history
CREATE TABLE IF NOT EXISTS driver_locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID REFERENCES drivers(id),
  lat DOUBLE PRECISION NOT NULL,
  lng DOUBLE PRECISION NOT NULL,
  accuracy REAL,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_driver_locations_driver_time ON driver_locations(driver_id, recorded_at DESC);

-- Booking audit trail
CREATE TABLE IF NOT EXISTS booking_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID REFERENCES bookings(id),
  event_type VARCHAR(50) NOT NULL,
  actor_type VARCHAR(20),
  actor_id UUID,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_booking_events_booking ON booking_events(booking_id);

-- SOS events
CREATE TABLE IF NOT EXISTS sos_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID REFERENCES drivers(id),
  booking_id UUID REFERENCES bookings(id),
  lat DOUBLE PRECISION,
  lng DOUBLE PRECISION,
  resolved BOOLEAN DEFAULT FALSE,
  resolved_by UUID,
  resolved_at TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- SMS log
CREATE TABLE IF NOT EXISTS sms_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  to_phone VARCHAR(20),
  body TEXT,
  status VARCHAR(20),
  twilio_sid VARCHAR(50),
  booking_id UUID REFERENCES bookings(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics cache (refresh every 15 min via APScheduler)
CREATE TABLE IF NOT EXISTS analytics_cache (
  key VARCHAR(100) PRIMARY KEY,
  value JSONB,
  computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fare configuration (singleton row)
CREATE TABLE IF NOT EXISTS fare_config (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  base_fare_cad DECIMAL(6,2) DEFAULT 3.50,
  per_km_rate_cad DECIMAL(6,2) DEFAULT 1.75,
  per_minute_wait_cad DECIMAL(6,2) DEFAULT 0.35,
  minimum_fare_cad DECIMAL(6,2) DEFAULT 8.00,
  hst_percent DECIMAL(4,2) DEFAULT 13.00,
  surge_multiplier DECIMAL(4,2) DEFAULT 1.0,
  surge_active BOOLEAN DEFAULT FALSE,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO fare_config DEFAULT VALUES ON CONFLICT DO NOTHING;

-- Scheduled rides column
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'cash';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS promo_code VARCHAR(30);
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancel_reason TEXT;

-- Driver fields
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS rating DECIMAL(3,2) DEFAULT 5.0;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS trips_completed INTEGER DEFAULT 0;
