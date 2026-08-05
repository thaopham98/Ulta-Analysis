from IPython.display import HTML, display
import pandas as pd

def show_swatches(dataset, start: int = 0, stop: int = 20, variants_df=None):
    # Convert pandas DataFrame / Series / list-like -> list[dict]
    if hasattr(dataset, "to_dict"):
        # DataFrame: to_dict("records") works
        if hasattr(dataset, "columns"):
            dataset = dataset.to_dict("records")
        else:
            # Series: convert index/value pairs into the expected dict format
            dataset = [
                {"product_id": idx, "variant_image_url": val}
                for idx, val in dataset.items()
            ]

    # Handle case where dataset is a list of strings (product IDs)
    # Convert to list of dicts if needed
    if dataset and isinstance(dataset[0], str):
        dataset = [{"product_id": pid, "variant_image_url": ""} for pid in dataset]

    # If dicts have no availability (e.g., dataset1), skip the filter gracefully
    filtered = []
    for x in dataset:
        if "availability" in x:
            if "OutOfStock" in str(x.get("availability", "")):
                continue
        filtered.append(x)

    # Get swatch images from variants DataFrame if provided
    product_swatches = {}
    if variants_df is not None:
        # Get unique product IDs from the filtered dataset
        for item in filtered:
            pid = str(item.get("product_id", ""))
            
            # Find all rows matching this product_id
            mask = variants_df["product_id"].astype(str) == pid
            matching_rows = variants_df[mask]
            
            # Collect valid swatch URLs
            swatches = []
            for _, row in matching_rows.iterrows():
                swatch_url = row.get("swatch_image_url", "")
                # Check if swatch_url is valid (not NaN, not empty)
                if pd.notna(swatch_url) and str(swatch_url).strip():
                    swatches.append(str(swatch_url))
            
            # Store unique swatches (remove duplicates)
            if swatches:
                product_swatches[pid] = list(dict.fromkeys(swatches))

    html = "<div style='display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;'>"
    for item in filtered[start:stop]:
        pid = str(item.get("product_id", ""))
        url = item.get("variant_image_url", "")
        
        # If no variant_image_url, try to get one from variants_df
        if not url and variants_df is not None:
            mask = variants_df["product_id"].astype(str) == pid
            matching_rows = variants_df[mask]
            if not matching_rows.empty:
                first_url = matching_rows.iloc[0].get("variant_image_url", "")
                if pd.notna(first_url):
                    url = first_url
        
        swatches = product_swatches.get(pid, [])

        html += f"""
        <div style='text-align: center;'>
            <img src="{url}" style='width: 200px; height: 200px; object-fit: cover; border-radius: 8px;'>
            <p style='font-size: 12px; margin-top: 5px;'>{pid}</p>
        """
        
        # Add swatch images if available
        if swatches:
            html += "<div style='display: flex; justify-content: center; gap: 5px; margin-top: 5px; flex-wrap: wrap;'>"
            for swatch_url in swatches:
                html += f"""
                    <img src="{swatch_url}" 
                         style='width: 40px; height: 40px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;'
                         title="Swatch">
                """
            html += "</div>"
        
        html += "</div>"

    html += "</div>"
    display(HTML(html))