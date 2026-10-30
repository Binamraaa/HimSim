## How the model works

The model treats the glacier as a 2D grid of columns of ice (50 m or 25 m cells). Each year, every column
**gains or loses ice at its surface** (mass balance) and **passes ice to its neighbours** (flow):

$$
\frac{\partial H}{\partial t} \;=\; \underbrace{\dot b(z)}_{\text{mass balance}} \;-\; \underbrace{\nabla \cdot \mathbf q}_{\text{ice flow}}
$$

where $H$ is ice thickness and $z = B + H$ is the surface elevation above the bed $B$.

### 1 · Mass balance: the climate part

A **degree-day model** is run for each month:

- Temperature at the glacier comes from the station temperature, cooled by the lapse rate:
  $T(z) = T_\text{station} + \Delta T - \gamma\,(z - z_\text{station})$, plus a seasonal cycle that peaks in July.
- **Melt** $= \text{DDF} \times \max(T - 0\,°\text{C},\,0) \times \text{days}$. The warmer the month, the more melt.
- **Snow** = precipitation × the fraction falling as snow (all snow below 0 °C, all rain above 2 °C).
  Precipitation increases with height and falls mostly in the monsoon.
- Mass balance = snow − melt. The elevation where it equals zero is the **equilibrium-line altitude (ELA)**.

Scenarios change $\Delta T$ and precipitation. Raising temperature by 1 °C moves the ELA up by roughly
$1/\gamma \approx 170$ m, which on a glacier that only spans ~600 m of elevation is a huge change.

### 2 · Ice flow: the Shallow Ice Approximation

Ice is a very viscous fluid that deforms under its own weight (Glen's flow law). In a glacier that is much
wider than it is thick, the flux of ice depends only on the local thickness and surface slope:

$$
\mathbf q = -D\,\nabla z, \qquad D = \Big(\Gamma\,H^{5} + \Gamma_s H^{3}\Big)\,|\nabla z|^{2}, \qquad
\Gamma = \tfrac{2A}{5}(\rho g)^3
$$

So ice "diffuses" down the surface slope, and **thick ice flows dramatically faster** ($H^5$!).
$A$ is the ice softness (the sidebar slider) and $\Gamma_s$ is optional basal sliding.

### 3 · Numerics

- **Staggered grid** (Mahaffy 1976): fluxes are computed on the faces between cells, so ice leaving one
  cell enters its neighbour exactly. Total mass is conserved by the flow.
- **Adaptive time step**: explicit diffusion is only stable for $\Delta t \le \Delta x^2 / (4 D_\max)$.
  The model picks the largest safe step automatically, so thick or steep ice means smaller steps.
- New ice can only *form* inside the initial glacier outline. Outside it the glacier can still flow and
  melt, but steep rock ridges don't grow glaciers (in reality snow avalanches off them).

### 4 · Getting the starting state

| Ingredient | Source |
|---|---|
| Ice surface 1981 | Your bias-corrected 1981 DEM |
| Terrain around the glacier | 2007 and 2015 DEMs (gaps interpolated) |
| Glacier outline | Randolph Glacier Inventory 6.0, RGI60-15.03954 (year 2000) |
| Ice thickness | Perfect-plasticity pattern $H = \tau / (\rho g \sin\alpha)$, scaled to the volume–area-scaling volume |
| Bed | surface − thickness |
| Climate calibration | Station temperature shifted until the modelled glacier-wide mass balance equals the observed 1981→2015 thinning |

### 5 · Known limitations (read before trusting a number)

- **No debris cover, avalanching, refreezing or snowpack memory.** Melt uses monthly mean temperatures only.
- **Ice thickness is estimated, not measured.** ±30–50 % is realistic, and it controls how long the glacier survives.
- **The climate defaults are approximate.** Replace them with Kyanjin station or ERA5 data for real studies.
- **Shallow-ice physics is less accurate on steep, short glaciers** like Yala (it ignores longitudinal stresses).
- The glacier outline is from 2000 but is used for the 1981 surface, so the 1981 extent is slightly underestimated.

This is a **learning and exploration tool**. Use it to build intuition about *why* glaciers respond the way they
do, not to make forecasts for decision-making.

### Further reading

- Cuffey & Paterson (2010), *The Physics of Glaciers*, ch. 5 (mass balance) and ch. 8 (flow).
- Oerlemans (2001), *Glaciers and Climate Change*: short and very readable.
- OGGM documentation (oggm.org): the open-source model used for glacier projections worldwide.
