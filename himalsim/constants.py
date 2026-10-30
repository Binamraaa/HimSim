"""Physical constants. SI units throughout, except that model time is in years."""

SECONDS_PER_YEAR = 31_556_926.0

RHO_ICE = 900.0  # kg m-3
RHO_WATER = 1000.0  # kg m-3
G = 9.81  # m s-2

# Glen's flow law: strain rate = A * stress^n
GLEN_N = 3.0
# Rate factor for temperate ice at 0 °C (Cuffey & Paterson 2010, Table 3.4), Pa-3 s-1
GLEN_A_TEMPERATE = 2.4e-24

# Convert metres water equivalent to metres of ice
WE_TO_ICE = RHO_WATER / RHO_ICE
