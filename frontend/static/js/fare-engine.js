/**
 * Caledonia Taxi — Client-Side Fare Engine
 * Must stay in sync with backend/services.py calculate_fare().
 * This is display-only; server is authoritative for payment amounts.
 *
 * fareEngine.estimate(legs, service, options) → breakdown
 *
 * legs: Array<{from: string, to: string, km: number}>
 * service: "standard" | "medical" | "long_distance"
 * options: {
 *   flatRates: {[city: string]: number}
 *   surgeMultiplier: number   (1.0 = no surge)
 *   promoDiscount: number     (0.0 to 1.0 fraction, e.g. 0.10 for 10%)
 *   stopSurcharge: number     ($ per intermediate stop)
 *   baseFare: number
 *   perKmRate: number
 *   minimumFare: number
 * }
 *
 * Returns:
 * {
 *   legs: [{label: string, km: number, subtotal: number}]
 *   base_fare: number
 *   stop_surcharge: number    (stopSurcharge × stop count)
 *   subtotal: number
 *   promo_discount: number    (negative value, 0 if no promo)
 *   surge_addition: number    (= subtotal × (surgeMultiplier - 1.0), 0 if no surge)
 *   total: number             (never below minimumFare)
 *   is_flat_rate: boolean
 * }
 *
 * Stop count = legs.length - 1  (intermediate stops only, not pickup/dropoff)
 *
 * For long_distance: flat rate from flatRates[dest] applied to legs[0].subtotal
 * For standard/medical: base_fare on first leg only, then per_km × km for all legs
 * Surge formula: surge_addition = subtotal × (surgeMultiplier - 1.0)
 * Promo formula: promo_discount = -(subtotal × promoDiscount)
 * Total = subtotal + promo_discount + surge_addition, minimum = minimumFare
 */
const fareEngine = (() => {
  function estimate(legs, service, options = {}) {
    const {
      flatRates = {},
      surgeMultiplier = 1.0,
      promoDiscount = 0.0,
      stopSurcharge = 3.00,
      baseFare = 4.50,
      perKmRate = 2.10,
      minimumFare = 8.00,
    } = options;

    if (!legs || legs.length === 0) {
      return { legs: [], base_fare: baseFare, stop_surcharge: 0, subtotal: 0, promo_discount: 0, surge_addition: 0, total: minimumFare, is_flat_rate: false };
    }

    const stopCount = Math.max(0, legs.length - 1);
    const isFlat = service === 'long_distance';
    let computedLegs = [];

    if (isFlat) {
      const dest = legs[legs.length - 1]?.to || '';
      const flat = flatRates[dest] ?? 0;
      computedLegs = legs.map((leg, i) => ({
        label: `${leg.from} → ${leg.to}`,
        km: leg.km || 0,
        subtotal: i === 0 ? round2(flat) : 0,
      }));
    } else {
      computedLegs = legs.map((leg, i) => ({
        label: `${leg.from} → ${leg.to}`,
        km: leg.km || 0,
        subtotal: round2((i === 0 ? baseFare : 0) + (leg.km || 0) * perKmRate),
      }));
    }

    const legTotal = round2(computedLegs.reduce((s, l) => s + l.subtotal, 0));
    const stopTotal = round2(stopCount * stopSurcharge);
    const subtotal = round2(legTotal + stopTotal);
    const promoAmt = round2(subtotal * promoDiscount);
    const surgeAmt = round2(subtotal * (surgeMultiplier - 1.0));
    const rawTotal = round2(subtotal - promoAmt + surgeAmt);
    const total = round2(Math.max(rawTotal, minimumFare));

    return {
      legs: computedLegs,
      base_fare: isFlat ? 0 : baseFare,
      stop_surcharge: stopTotal,
      subtotal,
      promo_discount: -promoAmt,
      surge_addition: surgeAmt,
      total,
      is_flat_rate: isFlat,
    };
  }

  function round2(n) {
    return Math.round((n || 0) * 100) / 100;
  }

  return { estimate };
})();
