## How the model works

### The big idea

A glacier is like a **bank account of ice**. Snow falling on it each year is money coming in; melting is money
going out. If more melts than falls, the glacier shrinks. On top of that, the ice **flows slowly downhill**,
moving ice from the snowy top to the warmer bottom, where it melts.

The model splits the glacier into a grid of squares (50 m or 25 m wide). For every square, every few days of
model time, it asks two questions:

1. **How much snow fell, and how much melted?** (the *mass balance*)
2. **How much ice flowed in from the neighbours, and how much flowed out?** (the *ice flow*)

### 1 · Snow in, melt out: the mass balance

- **Temperature drops as you climb**, about 6 °C for every kilometre. The model starts from the weather at Kyanjin
  village (3862 m) and works out how cold it is at every point on the glacier (5100–5700 m).
- **Melt:** in every month warmer than 0 °C, ice melts. The model uses a simple rule called the *degree-day
  method*: each degree above zero melts about 8 mm of water's worth of ice per day.
- **Snow:** precipitation falls as snow when it's below 0 °C and as rain above 2 °C. Most of it falls in the
  monsoon (June–September).
- The height where yearly snow exactly balances yearly melt is the **snowline**, which scientists call the
  **equilibrium-line altitude (ELA)**. Above it the glacier grows; below it, it shrinks.

> **Try it:** in *2 · Change the climate*, set +1 °C, choose "All at once", and open the *❓ Why?* tab. The snowline
> jumps up by roughly 150–200 m. Yala only spans about 600 m of height, so one degree is a lot.

### 2 · Ice flows like very thick honey

Ice looks solid, but under its own weight it slowly **deforms and flows**, like very stiff honey or putty. It
flows **downhill along the surface slope**, and **thick ice flows much faster than thin ice**: twice as thick
means about 30 times more flow. This is why thick glaciers move metres per day while thin ones barely creep.

The model uses the **Shallow Ice Approximation**, a standard simplification for glaciers that are much wider
than they are thick.

### 3 · Setting up Yala Glacier

| What the model needs | Where it comes from |
|---|---|
| Shape of the glacier surface in 1981 | Survey DEM (elevation map) of Yala, 1981 |
| Mountains around the glacier | Yala DEMs from 2007 and 2015, plus the free Copernicus GLO-30 DEM |
| Glacier outline | Randolph Glacier Inventory 6.0 (glacier RGI60-15.03954, mapped in 2000) |
| How thick the ice is | *Estimated*: ice is thickest where the surface is flattest, scaled so the total matches what similar-sized glaciers hold |
| Weather 1960–2025 | Kyanjin: ERA5-Land temperature + ERA5 precipitation, corrected to the station's measured 867 mm per year |
| Calibration | One temperature correction, chosen so that the 1981–2015 ice loss matches the DEMs |

**Heights are above sea level.** The Yala survey DEMs measured height from the *ellipsoid* (GPS height), which
is about 31 m different from sea level here. They're converted so everything matches the weather station and
ordinary maps. See the *Elevation maps* tab.

### 4 · Testing against reality

The model is only told one thing: the **average** ice loss between 1981 and 2015. Then it replays the weather
of each year, and we compare it with measurements it never saw (tab *3 · Can we trust it?*):

- the survey maps: did thinning **speed up** after 2007 (measured: from −0.44 to −0.91 m per year)?
- **radar**: in 2009 scientists measured the ice thickness by sending radio waves through the ice and timing the
  echo from the rock below. That gave the glacier's volume (61 million m³) and the thickness of its lower part in
  1982, 1996 and 2009 (60, 45 and 31 m) (Sugiyama et al. 2013).
- **stakes**: since 2011, ICIMOD scientists drill poles into the ice and measure how much of them melts out each
  year. Yala lost on average 0.80 m of water per year in 2011–2017, and the snowline sat between 5380 and 5518 m
  (Stumm et al. 2021).

With the standard settings it matches the volume, the thickness changes, the average yearly loss and the snowline.
It misses the ups and downs of individual years, and melt increases too slowly toward the snout. Both come from
using monthly temperatures only: real melt also depends on sunshine and on warm days within each month.

### 5 · What the model leaves out

Every model simplifies. This one does **not** include: rocks and debris lying on the ice (which can slow melting),
avalanches feeding snow onto the glacier, sunshine and shade (only air temperature drives melt), or day-to-day
weather (it uses monthly averages). The future scenarios are **"what if" experiments**, not predictions.

### For advanced students: the equations

Change of ice thickness $H$ with time = mass balance $\dot b$ minus the divergence of ice flux $\mathbf q$:

$$
\frac{\partial H}{\partial t} = \dot b(z) - \nabla\cdot\mathbf q,\qquad
\mathbf q = -\Gamma H^{5}\,|\nabla s|^{2}\,\nabla s,\qquad \Gamma = \tfrac{2A}{5}(\rho g)^3
$$

where $s$ is the surface elevation, $A$ is the ice softness (Glen's flow law, $n = 3$), $\rho$ the density of
ice and $g$ gravity. The equation is solved on a staggered grid (Mahaffy 1976) with an adaptive time step, and
the code is tested against the exact Halfar (1981) solution for a spreading ice dome.

**Further reading:** Oerlemans, *Glaciers and Climate Change* (2001), short and very readable · Cuffey & Paterson,
*The Physics of Glaciers* (2010) · AntarcticGlaciers.org, an excellent free site for students · OGGM-Edu (edu.oggm.org),
free interactive glacier lessons.
