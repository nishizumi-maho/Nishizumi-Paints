# Random Tab

The Random tab defines fallback policy. It decides who is eligible for fallback, which source the app should try first, and how the local fallback pool is managed.

## Step 1: Who should get fallback paints?

This step answers two separate questions:

1. should the app randomize cars, helmets, and suits at all?
2. should that happen for real drivers, AI drivers, or both?

The current layout keeps those scopes separate for:

- random cars
- random helmets
- random suits

This matters because a user might want:

- random cars for AI only
- random helmets for everyone
- no random suits at all

Easy mode exposes the essential version of this step directly so the user does not have to open the full Random tab just to control the basics.

## Step 2: Which fallback path should be preferred?

This step is about fallback source selection.

Typical options are:

- online fallback
- local fallback
- collection-pool behavior

The exact source order is then refined by the General tab worker and lane options and by whether the RandomPool or collection pool already contains usable assets.

## Step 3: Public showroom and Local RandomPool

Step 3 groups the two most important supporting systems together:

- the public showroom section
- the Local Random paints pool section

This is where the user manages the reusable local fallback cache and understands how public showroom imports interact with it.

## Local Random paints pool

The Local Random paints pool is the app’s reusable local cache of fallback assets.

It now lives here instead of the General tab because it is fundamentally a fallback-system feature, not a generic app setting.

Main controls include:

- enabling or disabling recycling of downloaded session paints into the pool
- total pool size
- per-category caps for cars, helmets, and suits
- opening or cleaning the pool
- rebuilding the pool from current files

### Important default

`Recycle downloaded TP car paints into the local random pool` is now off by default.

That means:

- manual showroom imports still remain in the pool
- manual collection imports still remain in the pool
- but normal live-session paints downloaded during monitoring are deleted after the session instead of being archived into the pool

## Easy mode explanation

In Easy mode, the text around the random fallback controls is intentionally simpler. The intent is to tell the user, clearly, that the app can assign a random online paint to a driver who does not have a usable Trading Paints paint.
