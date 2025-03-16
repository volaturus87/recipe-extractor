def extract_recipe(url):
    try:
        print(f"Extracting recipe from URL: {url}")
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Get all text content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title_tag = soup.find(['h1', 'h2'], class_=re.compile(r'title|recipe-title|entry-title', re.I))
        title = title_tag.text.strip() if title_tag else "Untitled Recipe"
        
        base_ingredients = []
        base_instructions = []
        variations = []

        # Extract recipe for FeelGoodFoodie
        if 'feelgoodfoodie.net' in url:
            # Ensure we are parsing the correct content area
            recipe_container = soup.find('div', class_='tasty-recipes')
            
            if recipe_container:
                # Extract Ingredients
                ingredients_section = recipe_container.find('ul', class_='tasty-recipes-ingredients')
                if ingredients_section:
                    ingredient_items = ingredients_section.find_all('li')
                    base_ingredients = [item.text.strip() for item in ingredient_items if item.text.strip()]
                
                # Extract Instructions
                instructions_section = recipe_container.find('ol', class_='tasty-recipes-method')
                if instructions_section:
                    instruction_items = instructions_section.find_all('li')
                    base_instructions = [clean_instruction(item.text, i) for i, item in enumerate(instruction_items) if clean_instruction(item.text)]
            
            if not base_ingredients or not base_instructions:
                return {'error': 'Unable to extract recipe details from this page. Please check the URL.'}
            
            # Handle variations if any
            variations = []

        # Clean up and validate
        base_ingredients = [i for i in base_ingredients if i]
        base_instructions = [i for i in base_instructions if i]
        variations = [v for v in variations if v['ingredients']]

        if not base_ingredients and not base_instructions and not variations:
            return {'error': 'Unable to extract recipe from this page. Please check if the URL is correct.'}

        result = {
            'title': title,
            'url': url,
            'base_ingredients': base_ingredients,
            'base_instructions': base_instructions,
            'variations': variations
        }
        return result

    except Exception as e:
        print(f"Error extracting recipe: {str(e)}")
        return {'error': 'An error occurred while extracting the recipe. Please try again.'}
