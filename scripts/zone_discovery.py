import math
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in kilometers between two points on the earth."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def scan_and_update_zones(db_session, PropertyModel, AreaModel):
    """
    Scans all properties, updates existing area metrics, and auto-discovers new areas.
    """
    logger.info("[Auto Zone] Starting radar scan...")
    
    areas = AreaModel.query.all()
    properties = PropertyModel.query.all()

    # Data structures to hold updates
    area_stats = {area.id: {'count': 0, 'total_price': 0} for area in areas}
    unassigned_properties = []

    # 1. Assign properties to existing areas (within 10 km radius)
    for prop in properties:
        if prop.latitude is None or prop.longitude is None:
            continue
            
        closest_area = None
        min_dist = float('inf')

        for area in areas:
            dist = haversine(prop.latitude, prop.longitude, area.latitude, area.longitude)
            if dist < min_dist:
                min_dist = dist
                closest_area = area

        if closest_area and min_dist <= 10.0:  # 10 km threshold for an existing zone
            area_stats[closest_area.id]['count'] += 1
            area_stats[closest_area.id]['total_price'] += prop.price
        else:
            unassigned_properties.append(prop)

    # 2. Update existing areas with new data
    for area in areas:
        stats = area_stats[area.id]
        if stats['count'] > 0:
            new_avg_price = stats['total_price'] / stats['count']
            # We add a slight bump to demand based on listing count to simulate market activity
            demand_boost = min(stats['count'] * 2, 20)  # max +20 demand
            
            # Update area values
            area.listing_count = stats['count']
            area.avg_price = new_avg_price
            
            # Note: We do NOT hardcode the score. The ML property in models.py will recalculate it!
            
    logger.info(f"[Auto Zone] Updated {len(areas)} existing zones with latest market data.")

    # 3. Auto-discover new areas from unassigned properties
    # We will cluster unassigned properties using a simple distance threshold
    clusters = []
    
    for prop in unassigned_properties:
        added_to_cluster = False
        for cluster in clusters:
            # Check distance to the first property in the cluster
            center_prop = cluster[0]
            dist = haversine(prop.latitude, prop.longitude, center_prop.latitude, center_prop.longitude)
            if dist <= 10.0: # 10 km radius for a new cluster
                cluster.append(prop)
                added_to_cluster = True
                break
        
        if not added_to_cluster:
            clusters.append([prop])

    # 4. Create new areas for clusters that are large enough (e.g., >= 2 properties)
    new_areas_count = 0
    for cluster in clusters:
        if len(cluster) >= 2:
            # Determine center point
            avg_lat = sum(p.latitude for p in cluster) / len(cluster)
            avg_lng = sum(p.longitude for p in cluster) / len(cluster)
            avg_price = sum(p.price for p in cluster) / len(cluster)
            
            # Determine name (most common city)
            city_counts = defaultdict(int)
            for p in cluster:
                city_name = p.city if p.city else p.location
                city_counts[city_name] += 1
            
            best_city = max(city_counts, key=city_counts.get)
            new_name = best_city
            
            # Create new Area
            new_area = AreaModel(
                name=new_name,
                latitude=avg_lat,
                longitude=avg_lng,
                avg_price=avg_price,
                listing_count=len(cluster),
                demand=50,       # Initial baseline for ML
                price_growth=10, # Initial baseline for ML
                services=50      # Initial baseline for ML
            )
            db_session.add(new_area)
            new_areas_count += 1
            logger.info(f"[Auto Zone] Discovered new zone: {new_name} at {avg_lat:.4f}, {avg_lng:.4f}")

    if new_areas_count > 0:
        logger.info(f"[Auto Zone] Successfully created {new_areas_count} new zones. ML will evaluate them immediately.")
        
    db_session.commit()
