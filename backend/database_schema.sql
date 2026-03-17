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
