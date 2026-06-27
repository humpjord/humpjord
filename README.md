# Off Market LA Image Generator

This is a small web service that takes listing data and a photo URL, and
returns a finished branded Instagram graphic (PNG) at a public URL.

## What you need to add before deploying
Copy your `off-market-template.svg` file (the one used by the Claude skill)
into this same folder. The app expects it to be named exactly:

    off-market-template.svg

## Deploying on Render (free tier)
1. Create a free account at render.com
2. Create a new GitHub repository and upload all files in this folder
   (app.py, requirements.txt, Dockerfile, off-market-template.svg)
3. In Render, click New, then Web Service, then connect that GitHub repo
4. Render will detect the Dockerfile automatically. Choose the Free instance type
5. Click Create Web Service. First deploy takes a few minutes
6. Once live, Render gives you a URL like https://offmarket-image-gen.onrender.com

## Using it
POST to https://yourapp.onrender.com/generate with JSON body:

    {
      "photo_url": "https://example.com/photo.jpg",
      "beds": "3",
      "baths": "3",
      "price": "$2,999,999",
      "neighborhood": "WESTCHESTER",
      "description": "Property description text, up to 300 characters."
    }

Response:

    { "image_url": "https://yourapp.onrender.com/images/abc123.png" }

That image_url is what gets passed to Instagram as the media URL.

## Note on free tier sleep
Render's free web services spin down after 15 minutes of no traffic.
The first request after it has been asleep takes about 30 to 50 seconds
to wake up. Every request after that is fast. For a once a day posting
workflow this just means the first call of the day is slow, which is fine
since nothing is watching it in real time.
