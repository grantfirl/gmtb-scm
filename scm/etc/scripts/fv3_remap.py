#!/usr/bin/env python

import numpy as np

r3 = 1./3.
r23 = 2./3.
r12 = 1./12.

def ppm_limiters(dm, a4, itot, lmt):
    # INPUT PARAMETERS: 
    #real , intent(in):: dm(*)     !< Linear slope
    #integer, intent(in) :: itot      !< Total Longitudes
    #integer, intent(in) :: lmt       !< 0: Standard PPM constraint 1: Improved full monotonicity constraint
    #                                      !< (Lin) 2: Positive definite constraint 
    #                                      !< 3: do nothing (return immediately)
    #! INPUT/OUTPUT PARAMETERS:
    #     real , intent(inout) :: a4(4,*)   !< PPM array AA <-- a4(1,i) AL <-- a4(2,i) AR <-- a4(3,i) A6 <-- a4(4,i)
    # ! LOCAL VARIABLES:
    #      real  qmp
    #      real  da1, da2, a6da
    #      real  fmin
    #      integer i

    #! Developer: S.-J. Lin
    if (lmt == 3):
        return a4
        
    if (lmt == 0):
    #! Standard PPM constraint
        for i in range(0,itot):
            if(dm[i] == 0.):
                a4[2,i] = a4[1,i]
                a4[3,i] = a4[1,i]
                a4[4,i] = 0.
            else:
                da1  = a4[3,i] - a4[2,i]
                da2  = da1*da1
                a6da = a4[4,i]*da1
                if(a6da < -da2):
                    a4[4,i] = 3.*(a4[2,i]-a4[1,i])
                    a4[3,i] = a4[2,i] - a4[4,i]
                elif(a6da > da2):
                    a4[4,i] = 3.*(a4[3,i]-a4[1,i])
                    a4[2,i] = a4[3,i] - a4[4,i]
    elif (lmt == 1):
    #! Improved full monotonicity constraint (Lin 2004)
    #! Note: no need to provide first guess of A6 <-- a4(4,i)
        for i in range(0,itot):
            qmp = 2.*dm[i]
            a4[2,i] = a4[1,i]-np.sign(qmp)[0]*np.min([np.abs(qmp),np.abs(a4[2,i]-a4[1,i])])
            a4[3,i] = a4[1,i]+np.sign(qmp)[0]*np.min([np.abs(qmp),np.abs(a4[3,i]-a4[1,i])])
            a4[4,i] = 3.*( 2.*a4[1,i] - (a4[2,i]+a4[3,i]) )
    elif (lmt == 2):
    #! Positive definite constraint
         for i in range(0,itot):
             if( np.abs(a4[3,i]-a4[2,i]) < -a4[4,i] ):
                 fmin = a4[1,i]+0.25*(a4[3,i]-a4[2,i])**2/a4[4,i]+a4[4,i]*r12
                 if( fmin < 0.):
                    if(a4[1,i] < a4[3,i] and a4[1,i] < a4[2,i]):
                        a4[3,i] = a4[1,i]
                        a4[2,i] = a4[1,i]
                        a4[4,i] = 0.
                    elif(a4[3,i] > a4[2,i]):
                        a4[4,i] = 3.*(a4[2,i]-a4[1,i])
                        a4[3,i] = a4[2,i] - a4[4,i]
                    else:
                        a4[4,i] = 3.*(a4[3,i]-a4[1,i])
                        a4[2,i] = a4[3,i] - a4[4,i]
    return a4

def cs_limiters(im, extm, a4, iv):
    #integer, intent(in) :: im
    #integer, intent(in) :: iv
    #logical, intent(in) :: extm(im)
    #real , intent(inout) :: a4(4,im)   !< PPM array
    #! LOCAL VARIABLES:
    #real  da1, da2, a6da
    #integer i
    
    if (iv == 0):
        #! Positive definite constraint
        for i in range(0,im):
            if (a4[0,i] <= 0.):
                a4[1,i] = a4[0,i]
                a4[2,i] = a4[0,i]
                a4[3,i] = 0.
            else:
                if (np.abs(a4[2,i]-a4[1,i]) < -a4[3,i]):
                    if ((a4[0,i]+0.25*(a4[2,i]-a4[1,i])**2/a4[3,i]+a4[3,i]*r12) < 0.):
                        #! local minimum is negative
                        if (a4[0,i] < a4[2,i] and a4[0,i] < a4[1,i]):
                            a4[2,i] = a4[0,i]
                            a4[1,i] = a4[0,i]
                            a4[3,i] = 0.
                        elif (a4[2,i] > a4[1,i]):
                            a4[3,i] = 3.*(a4[1,i]-a4[0,i])
                            a4[2,i] = a4[1,i] - a4[3,i]
                        else:
                            a4[3,i] = 3.*(a4[2,i]-a4[0,i])
                            a4[1,i] = a4[2,i] - a4[3,i]
    elif (iv == 1):
        for i in range(0,im):
            if ((a4[0,i]-a4[1,i])*(a4[0,i]-a4[2,i]) >= 0.):
                a4[1,i] = a4[0,i]
                a4[2,i] = a4[0,i]
                a4[3,i] = 0.
            else:
                da1  = a4[2,i] - a4[1,i]
                da2  = da1**2
                a6da = a4[3,i]*da1
                if (a6da < -da2):
                    a4[3,i] = 3.*(a4[1,i]-a4[0,i])
                    a4[2,i] = a4[1,i] - a4[3,i]
                elif (a6da > da2):
                    a4[3,i] = 3.*(a4[2,i]-a4[0,i])
                    a4[1,i] = a4[2,i] - a4[3,i]
    else:
        #! Standard PPM constraint
        for i in range(0,im):
            if (extm[i]):
                a4[1,i] = a4[0,i]
                a4[2,i] = a4[0,i]
                a4[3,i] = 0.
            else:
                da1  = a4[2,i] - a4[1,i]
                da2  = da1**2
                a6da = a4[3,i]*da1
                if (a6da < -da2):
                    a4[3,i] = 3.*(a4[1,i]-a4[0,i])
                    a4[2,i] = a4[1,i] - a4[3,i]
                elif (a6da > da2):
                    a4[3,i] = 3.*(a4[2,i]-a4[0,i])
                    a4[1,i] = a4[2,i] - a4[3,i]
    return a4

def ppm_profile(a4, delp, km, i1, i2, iv, kord):

     #! INPUT PARAMETERS:
     #integer, intent(in):: iv      !< iv =-1: winds iv = 0: positive definite scalars iv = 1: others iv = 2: temp (if remap_t) and w (iv=-2)
     #integer, intent(in):: i1      !< Starting longitude
     #integer, intent(in):: i2      !< Finishing longitude
     #integer, intent(in):: km      !< Vertical dimension
     #integer, intent(in):: kord    !< Order (or more accurately method no.):
     #real , intent(in):: delp(i1:i2,km)     !< Layer pressure thickness
     #!INPUT/OUTPUT PARAMETERS:
     #real , intent(inout):: a4(4,i1:i2,km)  !< Interpolated values
     #! DESCRIPTION:
     #!
     #!   Perform the piecewise parabolic reconstruction
     #! 
     #! !REVISION HISTORY: 
     #! S.-J. Lin   revised at GFDL 2007
     #!-----------------------------------------------------------------------
     #! local arrays:
     it = i2 - i1 + 1
     
     dc   = np.zeros((it,km))
     h2   = np.zeros((it,km))
     delq = np.zeros((it,km))
     df2  = np.zeros((it,km))
     d4   = np.zeros((it,km))
     #real    dc(i1:i2,km)
     #real    h2(i1:i2,km)
     #real  delq(i1:i2,km)
     #real   df2(i1:i2,km)
     #real    d4(i1:i2,km)

     #! local scalars:
     #integer i, k, km1, lmt, it
     #real  fac
     #real  a1, a2, c1, c2, c3, d1, d2
     #real  qm, dq, lac, qmp, pmp

     km1 = km - 1
     
     for k in range(2,km):
         for i in range(i1,i2):
             delq[i,k-1] =   a4[1,i,k] - a4[1,i,k-1]
             d4[i,k  ]   = delp[i,k-1] + delp[i,k]
     for k in range(2,km1):
         for i in range(i1,i2):
             c1  = (delp[i,k-1]+0.5*delp[i,k])/d4[i,k+1]
             c2  = (delp[i,k+1]+0.5*delp[i,k])/d4[i,k]
         df2[i,k] = delp[i,k]*(c1*delq[i,k] + c2*delq[i,k-1]) / (d4[i,k]+delp[i,k+1])
         dc[i,k] = np.sign(df2[i,k])*np.abs(np.min([np.abs(df2[i,k]), np.max([a4[1,i,k-1],a4[1,i,k],a4[1,i,k+1]])-a4[1,i,k], a4[1,i,k]-np.min([a4[1,i,k-1],a4[1,i,k],a4[1,i,k+1]])]))

    #!-----------------------------------------------------------
    #! 4th order interpolation of the provisional cell edge value
    #!-----------------------------------------------------------

     for k in range(3,km1):
         for i in range(i1,i2):
             c1 = delq[i,k-1]*delp[i,k-1] / d4[i,k]
             a1 = d4[i,k-1] / (d4[i,k] + delp[i,k-1])
             a2 = d4[i,k+1] / (d4[i,k] + delp[i,k])
             a4[2,i,k] = a4[1,i,k-1] + c1 + 2./(d4[i,k-1]+d4[i,k+1]) * (delp[i,k]*(c1*(a1 - a2)+a2*dc[i,k-1]) - delp[i,k-1]*a1*dc[i,k])

    #! Area preserving cubic with 2nd deriv. = 0 at the boundaries
    #! Top
     for i in range(i1,i2):
         d1 = delp[i,1]
         d2 = delp[i,2]
         qm = (d2*a4[1,i,1]+d1*a4[1,i,2]) / (d1+d2)
         dq = 2.*(a4[1,i,2]-a4[1,i,1]) / (d1+d2)
         c1 = 4.*(a4[2,i,3]-qm-d2*dq) / ( d2*(2.*d2*d2+d1*(d2+3.*d1)) )
         c3 = dq - 0.5*c1*(d2*(5.*d1+d2)-3.*d1*d1)
         a4[2,i,2] = qm - 0.25*c1*d1*d2*(d2+3.*d1)
         #! Top edge:
         #!-------------------------------------------------------
         a4[2,i,1] = d1*(2.*c1*d1**2-c3) + a4[2,i,2]
         #!-------------------------------------------------------
         #!        a4[2,i,1] = (12./7.)*a4[1,i,1]-(13./14.)*a4[1,i,2]+(3./14.)*a4[1,i,3]
         #!-------------------------------------------------------
         #! No over- and undershoot condition
         a4[2,i,2] = np.max([a4[2,i,2], np.min([a4[1,i,1], a4[1,i,2]])])
         a4[2,i,2] = np.min([a4[2,i,2], np.max([a4[1,i,1], a4[1,i,2]])])
         dc[i,1] =  0.5*(a4[2,i,2] - a4[1,i,1])

         #! Enforce monotonicity  within the top layer

     if (iv == 0):
        for i in range(i1,i2):
           a4[2,i,1] = np.max([0., a4[2,i,1]])
           a4[2,i,2] = np.max([0., a4[2,i,2]])
     elif (iv == -1):
         for i in range(i1,i2):
             if (a4[2,i,1]*a4[1,i,1] <= 0. ):
                  a4[2,i,1] = 0.
     elif (np.abs(iv) == 2):
         for i in range(i1,i2):
             a4[2,i,1] = a4[1,i,1]
             a4[3,i,1] = a4[1,i,1]

     #! Bottom
     #! Area preserving cubic with 2nd deriv. = 0 at the surface
     for i in range(i1,i2):
         d1 = delp[i,km]
         d2 = delp[i,km1]
         qm = (d2*a4[1,i,km]+d1*a4[1,i,km1]) / (d1+d2)
         dq = 2.*(a4[1,i,km1]-a4[1,i,km]) / (d1+d2)
         c1 = (a4[2,i,km1]-qm-d2*dq) / (d2*(2.*d2*d2+d1*(d2+3.*d1)))
         c3 = dq - 2.0*c1*(d2*(5.*d1+d2)-3.*d1*d1)
         a4[2,i,km] = qm - c1*d1*d2*(d2+3.*d1)
         #! Bottom edge:
         #!-----------------------------------------------------
         a4[3,i,km] = d1*(8.*c1*d1**2-c3) + a4[2,i,km]
         #!        dc[i,km] = 0.5*(a4[3,i,km] - a4[1,i,km])
         #!-----------------------------------------------------
         #!        a4[3,i,km] = (12./7.)*a4[1,i,km]-(13./14.)*a4[1,i,km-1]+(3./14.)*a4[1,i,km-2]
         #! No over- and under-shoot condition
         a4[2,i,km] = np.max([a4[2,i,km], np.min([a4[1,i,km], a4[1,i,km1]])])
         a4[2,i,km] = np.min([a4[2,i,km], np.max([a4[1,i,km], a4[1,i,km1]])])
         dc[i,km] = 0.5*(a4[1,i,km] - a4[2,i,km])


     #! Enforce constraint on the "slope" at the surface

     ##ifdef BOT_MONO
     #     do i=i1,i2
     #        a4(4,i,km) = 0
     #        if( a4(3,i,km) * a4(1,i,km) <= 0. ) a4(3,i,km) = 0.
     #        d1 = a4(1,i,km) - a4(2,i,km)
     #        d2 = a4(3,i,km) - a4(1,i,km)
     #        if ( d1*d2 < 0. ) then
     #             a4(2,i,km) = a4(1,i,km)
     #             a4(3,i,km) = a4(1,i,km)
     #        else
     #             dq = sign(min(abs(d1),abs(d2),0.5*abs(delq(i,km-1))), d1)
     #             a4(2,i,km) = a4(1,i,km) - dq
     #             a4(3,i,km) = a4(1,i,km) + dq
     #        endif
     #     enddo
     ##else
     if (iv == 0):
         for i in range(i1,i2):
            a4[2,i,km] = np.max([0.,a4[2,i,km]])
            a4[3,i,km] = np.max([0.,a4[3,i,km]])
     elif (iv < 0):
         for i in range(i1,i2):
             if (a4[1,i,km]*a4[3,i,km] <= 0.):
                 a4[3,i,km] = 0.
     ##endif

     for k in range(1,km1):
         for i in range(i1,i2):
            a4[3,i,k] = a4[2,i,k+1]

     #!-----------------------------------------------------------
     #! f(s) = AL + s*[(AR-AL) + A6*(1-s)]         ( 0 <= s  <= 1 )
     #!-----------------------------------------------------------
     #! Top 2 and bottom 2 layers always use monotonic mapping
     for k in range(1,2):
         for i in range(i1,i2):
             a4[4,i,k] = 3.*(2.*a4[1,i,k] - (a4[2,i,k]+a4[3,i,k]))
         a4[:,:,k] = ppm_limiters(dc[:,k], a4[:,:,k], it, 0)

     if (kord >= 7):
         #!-----------------------
         #! Huynh's 2nd constraint
         #!-----------------------
         for k in range(2,km1):
             for i in range(i1,i2):
                 #! Method#1
                 #!           h2[i,k] = delq[i,k] - delq[i,k-1]
                 #! Method#2 - better
                 h2[i,k] = 2.*(dc[i,k+1]/delp[i,k+1] - dc[i,k-1]/delp[i,k-1]) / (delp[i,k]+0.5*(delp[i,k-1]+delp[i,k+1])) * delp[i,k]**2 
                 #! Method#3
                 #!!!         h2[i,k] = dc[i,k+1] - dc[i,k-1]
         fac = 1.5           #! original quasi-monotone
         
         for k in range(3,km-2):
             for i in range(i1,i2):
                 #! Right edges
                 #!        qmp   = a4[1,i,k] + 2.0*delq[i,k-1]
                 #!        lac   = a4[1,i,k] + fac*h2[i,k-1] + 0.5*delq[i,k-1]
                 pmp   = 2.*dc[i,k]
                 qmp   = a4[1,i,k] + pmp
                 lac   = a4[1,i,k] + fac*h2[i,k-1] + dc[i,k]
                 a4[3,i,k] = np.min([np.max([a4[3,i,k], np.min([a4[1,i,k], qmp, lac])]), np.max([a4[1,i,k], qmp, lac])])
                 #! Left  edges
                 #!        qmp   = a4[1,i,k] - 2.0*delq[i,k]
                 #!        lac   = a4[1,i,k] + fac*h2[i,k+1] - 0.5*delq[i,k]
                 #!
                 qmp   = a4[1,i,k] - pmp
                 lac   = a4[1,i,k] + fac*h2[i,k+1] - dc[i,k]
                 a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[1,i,k], qmp, lac])]), np.max([a4[1,i,k], qmp, lac])])
                 #!-------------
                 #! Recompute A6
                 #!-------------
                 a4[4,i,k] = 3.*(2.*a4[1,i,k] - (a4[2,i,k]+a4[3,i,k]))
             #! Additional constraint to ensure positivity when kord=7
             if (iv == 0 and kord >= 6):
                 a4[:,:,k] = ppm_limiters(dc[:,k], a4[:,:,k], it, 2)
     else:
        lmt = kord - 3
        lmt = np.max([0, lmt])
        if (iv == 0):
            lmt = np.min([2, lmt])

        for k in range(3,km-2):
            if( kord != 4):
                for i in range(i1,i2):
                    a4[4,i,k] = 3.*(2.*a4[1,i,k] - (a4[2,i,k]+a4[3,i,k]))
             
            if(kord != 6):
                 a4[:,:,k] = ppm_limiters(dc[:,k], a4[:,:,k], it, lmt)

     for k in range(km1,km):
         for i in range(i1,i2):
             a4[4,i,k] = 3.*(2.*a4[1,i,k] - (a4[2,i,k]+a4[3,i,k]))
         a4[:,:,k] = ppm_limiters(dc[:,k], a4[:,:,k], it, 0)

def scalar_profile(qs, a4, delp, km, i1, i2, iv, kord, qmin):
    #! Optimized vertical profile reconstruction:
    #! Latest: Apr 2008 S.-J. Lin, NOAA/GFDL
    #integer, intent(in):: i1, i2
    #integer, intent(in):: km      !< vertical dimension
    #integer, intent(in):: iv      !< iv =-1: winds iv = 0: positive definite scalars iv = 1: others
    #integer, intent(in):: kord
    #real, intent(in)   ::   qs(i1:i2)
    #real, intent(in)   :: delp(i1:i2,km)     !< Layer pressure thickness
    #real, intent(inout):: a4(4,i1:i2,km)     !< Interpolated values
    #real, intent(in):: qmin
    #!-----------------------------------------------------------------------
    im = i2 - i1 + 1
    extm = np.zeros([im,km],dtype=bool)
    ext5 = np.zeros([im,km],dtype=bool)
    ext6 = np.zeros([im,km],dtype=bool)
    
    gam = np.zeros([im,km])
    q   = np.zeros([im,km+1])
    d4  = np.zeros([im])
    
    #logical, dimension(i1:i2,km):: extm, ext5, ext6
    #real  gam(i1:i2,km)
    #real    q(i1:i2,km+1)
    #real   d4(i1:i2)
    #real   bet, a_bot, grat 
    #real   pmp_1, lac_1, pmp_2, lac_2, x0, x1
    #integer i, k, im
    
    if (iv == -2):
        for i in range(0,im):
            gam[i,1] = 0.5
            q[i,0] = 1.5*a4[0,i,0]
        for k in range(1,km-1):
            for i in range(0,im):
                grat = delp[i,k-1] / delp[i,k]
                bet =  2. + grat + grat - gam[i,k]
                q[i,k] = (3.*(a4[0,i,k-1]+a4[0,i,k]) - q[i,k-1])/bet
                gam[i,k+1] = grat / bet
        for i in range(0,im):
           grat = delp[i,km-2] / delp[i,km-1]
           q[i,km-1] = (3.*(a4[0,i,km-2]+a4[0,i,km-1]) - grat*qs[i] - q[i,km-2]) / (2. + grat + grat - gam[i,km-1])
           q[i,km] = qs[i]
        for k in range(km-2,-1,-1):
            for i in range(0,im):
                q[i,k] = q[i,k] - gam[i,k+1]*q[i,k+1]
    else:
        for i in range(0,im):
            grat = delp[i,1] / delp[i,0]   #! grid ratio
            bet = grat*(grat+0.5)
            q[i,0] = ((grat+grat)*(grat+1.)*a4[0,i,0] + a4[0,i,1]) / bet
            gam[i,0] = ( 1. + grat*(grat+1.5) ) / bet
        for k in range(1,km):
            for i in range(0,im):
                d4[i] = delp[i,k-1] / delp[i,k]
                bet =  2. + d4[i] + d4[i] - gam[i,k-1]
                q[i,k] = ( 3.*(a4[0,i,k-1]+d4[i]*a4[0,i,k]) - q[i,k-1] )/bet
                gam[i,k] = d4[i] / bet
        for i in range(0,im):
            a_bot = 1. + d4[i]*(d4[i]+1.5)
            q[i,km] = (2.*d4[i]*(d4[i]+1.)*a4[0,i,km-1]+a4[0,i,km-2]-a_bot*q[i,km-1]) / ( d4[i]*(d4[i]+0.5) - a_bot*gam[i,km-1])
        for k in range(km-1,-1,-1):
            for i in range(0,im):
                q[i,k] = q[i,k] - gam[i,k]*q[i,k+1]
    

    #!----- Perfectly linear scheme --------------------------------
    if (np.abs(kord) > 16):
        for k in range(0,km):
            for i in range(0,im):
                a4[1,i,k] = q[i,k]
                a4[2,i,k] = q[i,k+1]
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        return a4

    #!----- Perfectly linear scheme --------------------------------
    #!------------------
    #! Apply constraints
    #!------------------
    
    #! Apply *large-scale* constraints 
    for i in range(0,im):
        q[i,1] = np.min([q[i,1], np.max([a4[0,i,0], a4[0,i,1]])])
        q[i,1] = np.max([q[i,1], np.min([a4[0,i,0], a4[0,i,1]])])
    
    for k in range(1,km):
        for i in range(0,im):
            gam[i,k] = a4[0,i,k] - a4[0,i,k-1]
    
    #! Interior:
    for k in range(2,km-1):
        for i in range(0,im):
            if (gam[i,k-1]*gam[i,k+1] > 0.):
                #! Apply large-scale constraint to ALL fields if not local max/min
                q[i,k] = np.min([q[i,k], np.max([a4[0,i,k-1],a4[0,i,k]])])
                q[i,k] = np.max([q[i,k], np.min([a4[0,i,k-1],a4[0,i,k]])])
            else:
                if (gam[i,k-1] > 0):
                    #! There exists a local max
                    q[i,k] = np.max([q[i,k], np.min([a4[0,i,k-1],a4[0,i,k]])])
                else:
                    #! There exists a local min
                    q[i,k] = np.min([q[i,k], np.max([a4[0,i,k-1],a4[0,i,k]])])
                    if (iv == 0):
                        q[i,k] = np.max([0., q[i,k]])

    #! Bottom:
    for i in range(0,im):
        q[i,km-1] = np.min([q[i,km-1], np.max([a4[0,i,km-2], a4[0,i,km-1]])])
        q[i,km-1] = np.max([q[i,km-1], np.min([a4[0,i,km-2], a4[0,i,km-1]])])

    for k in range(0,km):
        for i in range(0,im):
            a4[1,i,k] = q[i,k  ]
            a4[2,i,k] = q[i,k+1]
    
    for k in range(0,km):
        if (k == 0 or k == km-1):
            for i in range(0,im):
                extm[i,k] = (a4[1,i,k]-a4[0,i,k]) * (a4[2,i,k]-a4[0,i,k]) > 0.
        else:
            for i in range(0,im):
                extm[i,k] = gam[i,k]*gam[i,k+1] < 0.
        if ( np.abs(kord) > 9 ):
            for i in range(0,im):
                x0 = 2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k])
                x1 = np.abs(a4[1,i,k]-a4[2,i,k])
                a4[3,i,k] = 3.*x0
                ext5[i,k] = np.abs(x0) > x1
                ext6[i,k] = np.abs(a4[3,i,k]) > x1

    #!---------------------------
    #! Apply subgrid constraints:
    #!---------------------------
    #! f(s) = AL + s*[(AR-AL) + A6*(1-s)]         ( 0 <= s  <= 1 )
    #! Top 2 and bottom 2 layers always use monotonic mapping

    if (iv == 0):
        for i in range(0,im):
            a4[1,i,0] = np.max([0., a4[1,i,0]])
    elif (iv == -1):
        for i in range(0,im):
            if ( a4[1,i,0]*a4[0,i,0] <= 0. ):
                a4[1,i,0] = 0.
    elif (iv == 2):
        for i in range(0,im):
            a4[1,i,0] = a4[0,i,0]
            a4[2,i,0] = a4[0,i,0]
            a4[3,i,0] = 0.
            
    if (iv != 2):
        for i in range(0,im):
            a4[3,i,0] = 3.*(2.*a4[0,i,0] - (a4[1,i,0]+a4[2,i,0]))
        a4[:,:,0] = cs_limiters(im, extm[:,0], a4[:,:,0], 1)
    
    #! k=1
    for i in range(0,im):
        a4[3,i,1] = 3.*(2.*a4[0,i,1] - (a4[1,i,1]+a4[2,i,1]))
    a4[:,:,1] = cs_limiters(im, extm[:,1], a4[:,:,1], 2)
    
    #!-------------------------------------
    #! Huynh's 2nd constraint for interior:
    #!-------------------------------------
    for k in range(2,km-2):
        if (np.abs(kord) < 9):
            for i in range(0,im):
                #! Left  edges
                pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                lac_1 = pmp_1 + 1.5*gam[i,k+2]
                a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                #! Right edges
                pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                lac_2 = pmp_2 - 1.5*gam[i,k-1]
                a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])

                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        elif (np.abs(kord) == 9):
            for i in range(0,im):
                if (extm[i,k] and extm[i,k-1]):
                    #! grid-scale 2-delta-z wave detected
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                    a4[3,i,k] = 0.
                elif (extm[i,k] and extm[i,k+1]):
                    #! grid-scale 2-delta-z wave detected
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                    a4[3,i,k] = 0.
                elif (extm[i,k] and a4[0,i,k] < qmin):
                    #! grid-scale 2-delta-z wave detected
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                    a4[3,i,k] = 0.
                else:
                    a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
                    #! Check within the smooth region if subgrid profile is non-monotonic
                    if(np.abs(a4[3,i,k]) > np.abs(a4[1,i,k]-a4[2,i,k])):
                        pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                        lac_1 = pmp_1 + 1.5*gam[i,k+2]
                        a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                        pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                        lac_2 = pmp_2 - 1.5*gam[i,k-1]
                        a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
                        a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))

        elif (np.abs(kord) == 10):
            for i in range(0,im):
                if (ext5[i,k]):
                    if (ext5[i,k-1] or ext5[i,k+1]):
                        a4[1,i,k] = a4[0,i,k]
                        a4[2,i,k] = a4[0,i,k]
                    elif (ext6[i,k-1] or ext6[i,k+1]):
                        pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                        lac_1 = pmp_1 + 1.5*gam[i,k+2]
                        a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                        pmp_2 = a4[1,i,k] + 2.*gam[i,k]
                        lac_2 = pmp_2 - 1.5*gam[i,k-1]
                        a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
                elif (ext6[i,k]):
                    if (ext5[i,k-1] or ext5[i,k+1]):
                        pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                        lac_1 = pmp_1 + 1.5*gam[i,k+2]
                        a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                        pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                        lac_2 = pmp_2 - 1.5*gam[i,k-1]
                        a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
            for i in range(0,im):
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        elif (np.abs(kord) == 12):
            for i in range(0,im):
                if (extm[i,k]):
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                    a4[3,i,k] = 0.
                else:        #! not a local extremum
                    a4[3,i,k] = 6.*a4[0,i,k] - 3.*(a4[1,i,k]+a4[2,i,k])
                    #! Check within the smooth region if subgrid profile is non-monotonic
                    if (np.abs(a4[3,i,k]) > np.abs(a4[1,i,k]-a4[2,i,k])):
                        pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                        lac_1 = pmp_1 + 1.5*gam[i,k+2]
                        a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                        pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                        lac_2 = pmp_2 - 1.5*gam[i,k-1]
                        a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
                        a4[3,i,k] = 6.*a4[0,i,k] - 3.*(a4[1,i,k]+a4[2,i,k])
        elif (np.abs(kord) == 13):
            for i in range(0,im):
                if (ext6[i,k]):
                    if (ext6[i,k-1] and ext6[i,k+1]):
                        #! grid-scale 2-delta-z wave detected
                        a4[1,i,k] = a4[0,i,k]
                        a4[2,i,k] = a4[0,i,k]
            for i in range(0,im):
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        elif (np.abs(kord) == 14):
            for i in range(0,im):
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        elif (np.abs(kord) == 15):   #! Revised abs(kord)=9 scheme
            for i in range(0,im):
                if (ext5[i,k] and ext5[i,k-1]):
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                elif (ext5[i,k] and ext5[i,k+1]):
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                elif (ext5[i,k] and a4[0,i,k] < qmin):
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                elif (ext6[i,k]):
                    pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                    lac_1 = pmp_1 + 1.5*gam[i,k+2]
                    a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                    pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                    lac_2 = pmp_2 - 1.5*gam[i,k-1]
                    a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
            for i in range(0,im):
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        elif (np.abs(kord) == 16):
            for i in range(0,im):
                if (ext5[i,k]):
                    if (ext5[i,k-1] or ext5[i,k+1]):
                        a4[1,i,k] = a4[0,i,k]
                        a4[2,i,k] = a4[0,i,k]
                    elif (ext6[i,k-1] or ext6[i,k+1]):
                        #! Left  edges
                        pmp_1 = a4[0,i,k] - 2.*gam[i,k+1]
                        lac_1 = pmp_1 + 1.5*gam[i,k+2]
                        a4[1,i,k] = np.min([np.max([a4[1,i,k], np.min([a4[0,i,k], pmp_1, lac_1])]), np.max([a4[0,i,k], pmp_1, lac_1])])
                        #! Right edges
                        pmp_2 = a4[0,i,k] + 2.*gam[i,k]
                        lac_2 = pmp_2 - 1.5*gam[i,k-1]
                        a4[2,i,k] = np.min([np.max([a4[2,i,k], np.min([a4[0,i,k], pmp_2, lac_2])]), np.max([a4[0,i,k], pmp_2, lac_2])])
            for i in range(0,im):
                a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        else:      #! kord = 11, 13
            for i in range(0,im):
                if (ext5[i,k] and (ext5[i,k-1] or ext5[i,k+1] or a4[0,i,k] < qmin)):
                    #! Noisy region:
                    a4[1,i,k] = a4[0,i,k]
                    a4[2,i,k] = a4[0,i,k]
                    a4[3,i,k] = 0.
                else:
                    a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
                    
        #! Additional constraint to ensure positivity
        if (iv == 0):
            a4[:,:,k] = cs_limiters(im, extm[:,k], a4[:,:,k], 0)

    ####end for k in range(3,km-2)

    #!----------------------------------
    #! Bottom layer subgrid constraints:
    #!----------------------------------
    if (iv == 0):
        for i in range(0,im):
            a4[2,i,km-1] = np.max([0., a4[2,i,km-1]])
    elif (iv == -1):
        for i in range(0,im): 
            if (a4[2,i,km-1]*a4[0,i,km-1] <= 0.):
                a4[2,i,km-1] = 0.

    for k in range(km-2,km):
        for i in range(0,im):
            a4[3,i,k] = 3.*(2.*a4[0,i,k] - (a4[1,i,k]+a4[2,i,k]))
        if (k == (km-2)):
            a4[:,:,k] = cs_limiters(im, extm[:,k], a4[:,:,k], 2)
        if (k == km-1):
            a4[:,:,k] = cs_limiters(im, extm[:,k], a4[:,:,k], 1)

    return a4

def map_scalar(km, pe1, q1, qs, kn, pe2, i1, i2, iv, kord, q_min):
    #! iv=1
    #integer, intent(in) :: i1                !< Starting longitude
    #integer, intent(in) :: i2                !< Finishing longitude
    #integer, intent(in) :: iv                !< Mode: 0 == constituents 1 == temp 2 == remap temp with cs scheme
    #integer, intent(in) :: kord              !< Method order
    #integer, intent(in) :: km                !< Original vertical dimension
    #integer, intent(in) :: kn                !< Target vertical dimension
    #real, intent(in) ::   qs(i1:i2)       !< bottom BC
    #real, intent(in) ::  pe1(i1:i2,km+1)  !< pressure at layer edges from model top to bottom surface in the original vertical coordinate
    #real, intent(in) ::  pe2(i1:i2,kn+1)  !< pressure at layer edges from model top to bottom surface in the new vertical coordinate
    #real, intent(in) ::    q1(ibeg:iend,km) !< Field input
    #! INPUT/OUTPUT PARAMETERS:
    #real, intent(inout)::  q2(ibeg:iend,kn) !< Field output
    
    im = i2 - i1 + 1
    q2 = np.zeros([im,kn])
    #real, intent(in):: q_min

    #! DESCRIPTION:
    #! IV = 0: constituents
    #! pe1: pressure at layer edges (from model top to bottom surface)
    #!      in the original vertical coordinate
    #! pe2: pressure at layer edges (from model top to bottom surface)
    #!      in the new vertical coordinate
    #! LOCAL VARIABLES:
    dp1 = np.zeros([im,km])
    q4  = np.zeros([4,im,km])
    #real    dp1(i1:i2,km)
    #real   q4(4,i1:i2,km)
    #real    pl, pr, qsum, dp, esl
    #integer i, k, l, m, k0
    
    for k in range(0,km):
        for i in range(0,im):
            dp1[i,k] = pe1[i,k+1] - pe1[i,k]
            q4[0,i,k] = q1[i,k]
    
    #! Compute vertical subgrid distribution
    if (kord > 7):
       #print qs, q4, dp1, km, i1, i2, iv, kord, q_min
       q4 = scalar_profile(qs, q4, dp1, km, i1, i2, iv, kord, q_min)
    else:
       q4 = ppm_profile(q4, dp1, km, i1, i2, iv, kord)
    
    for i in range(0,im):
        k0 = 0
        for k in range(0,kn):
            next_k = False
            for l in range(k0,km):  #AKA l-loop
                #! locate the top edge: pe2(i,k)
                if (pe2[i,k] >= pe1[i,l] and pe2[i,k] <= pe1[i,l+1]):
                    pl = (pe2[i,k]-pe1[i,l]) / dp1[i,l]
                    if (pe2[i,k+1] <= pe1[i,l+1]):
                        #! entire new grid is within the original grid
                        pr = (pe2[i,k+1]-pe1[i,l]) / dp1[i,l]
                        q2[i,k] = q4[1,i,l] + 0.5*(q4[3,i,l]+q4[2,i,l]-q4[1,i,l]) * (pr+pl)-q4[3,i,l]*r3*(pr*(pr+pl)+pl**2)
                        k0 = l
                        next_k = True
                        break
                        #goto 555 #(next iteration of "for k in range(1,kn):" loop)
                    else:
                        #! Fractional area...
                        qsum = (pe1[i,l+1]-pe2[i,k])*(q4[1,i,l]+0.5*(q4[3,i,l]+q4[2,i,l]-q4[1,i,l])*(1.+pl)-q4[3,i,l]*(r3*(1.+pl*(1.+pl))))
                        for m in range(l+1,km): #AKA m-loop
                            #! locate the bottom edge: pe2(i,k+1)
                            if (pe2[i,k+1] > pe1[i,m+1]):
                                #! Whole layer
                                qsum = qsum + dp1[i,m]*q4[0,i,m]
                            else:
                                dp = pe2[i,k+1]-pe1[i,m]
                                esl = dp / dp1[i,m]
                                qsum = qsum + dp*(q4[1,i,m]+0.5*esl*(q4[2,i,m]-q4[1,i,m]+q4[3,i,m]*(1.-r23*esl)))
                                k0 = m
                                #goto 123 #(exit out of l-loop)
                                break
                        else:
                            break #handles goto 123 statement below (exits out of l-loop even if m-loop successfully completes)
                            #continue
                        break
                        #goto 123 #(right before going to next iteration of "for k in range(1,kn):" loop)
            if not next_k:
                q2[i,k] = qsum / (pe2[i,k+1] - pe2[i,k]) #AKA label 123
    return q2

def map1_q2 (km, pe1, q1, kn, pe2, dp2, i1, i2, iv, kord, q_min):
    #! INPUT PARAMETERS:
    #integer, intent(in) :: i1, i2
    #integer, intent(in) :: iv                !< Mode: 0 ==  constituents 1 == ???
    #integer, intent(in) :: kord
    #integer, intent(in) :: km                !< Original vertical dimension
    #integer, intent(in) :: kn                !< Target vertical dimension
    #real, intent(in) ::  pe1(i1:i2,km+1)     !< pressure at layer edges from model top to bottom surface in the original vertical coordinate
    #real, intent(in) ::  pe2(i1:i2,kn+1)     !< pressure at layer edges from model top to bottom surface in the new vertical coordinate
    #real, intent(in) ::  q1(i1:i2,km) !< Field input
    #real, intent(in) ::  dp2(i1:i2,kn)
    #real, intent(in) ::  q_min
    #! INPUT/OUTPUT PARAMETERS:
    im = i2 - i1 + 1
    q2 = np.zeros([im,kn])
    #real, intent(inout):: q2(i1:i2,kn) !< Field output
    #! LOCAL VARIABLES:
    im = i2 - i1 + 1
    qs = np.zeros([im])
    dp1 = np.zeros([im,km])
    q4 = np.zeros([4,im,km])
    #real   qs(i1:i2)
    #real   dp1(i1:i2,km)
    #real   q4(4,i1:i2,km)
    #real   pl, pr, qsum, dp, esl
    #integer i, k, l, m, k0

    for k in range(0,km):
        for i in range(0,im):
            dp1[i,k] = pe1[i,k+1] - pe1[i,k]
            q4[0,i,k] = q1[i,k]
    
    #! Compute vertical subgrid distribution
    if (kord > 7):
       q4 = scalar_profile (qs, q4, dp1, km, i1, i2, iv, kord, q_min)
    else:
       q4 = ppm_profile (q4, dp1, km, i1, i2, iv, kord)
    
    #! Mapping
    for i in range(0,im):
        k0 = 0
        for k in range(0,kn):
            next_k = False
            #print 'k new = ',k
            for l in range(k0,km):
                #print 'l old = ',l
                #! locate the top edge: pe2(i,k)
                if (pe2[i,k] >= pe1[i,l] and pe2[i,k] <= pe1[i,l+1]):
                    pl = (pe2[i,k]-pe1[i,l]) / dp1[i,l]
                    if (pe2[i,k+1] <= pe1[i,l+1]):
                        #! entire new grid is within the original grid
                        pr = (pe2[i,k+1]-pe1[i,l]) / dp1[i,l]
                        q2[i,k] = q4[1,i,l] + 0.5*(q4[3,i,l]+q4[2,i,l]-q4[1,i,l])*(pr+pl)-q4[3,i,l]*r3*(pr*(pr+pl)+pl**2)
                        k0 = l
                        next_k = True
                        #print 'new grid within old; q2 = ', q2[i,k]
                        break
                        #goto 555 #next k-loop iteration
                    else:
                        #! Fractional area...
                        print k, (pe1[i,l+1]-pe2[i,k]), (q4[1,i,l]+0.5*(q4[3,i,l]+q4[2,i,l]-q4[1,i,l])*(1.+pl)-q4[3,i,l]*(r3*(1.+pl*(1.+pl)))), dp2[i,k]
                        qsum = (pe1[i,l+1]-pe2[i,k])*(q4[1,i,l]+0.5*(q4[3,i,l]+q4[2,i,l]-q4[1,i,l])*(1.+pl)-q4[3,i,l]*(r3*(1.+pl*(1.+pl))))
                        for m in range(l+1,km):
                            #! locate the bottom edge: pe2(i,k+1)
                            if (pe2[i,k+1] > pe1[i,m+1]):
                                #! Whole layer..
                                qsum = qsum + dp1[i,m]*q4[0,i,m]
                                #print 'whole layer, m = ',m
                            else:
                                dp = pe2[i,k+1]-pe1[i,m]
                                esl = dp / dp1[i,m]
                                qsum = qsum + dp*(q4[1,i,m]+0.5*esl*(q4[2,i,m]-q4[1,i,m]+q4[3,i,m]*(1.-r23*esl)))
                                k0 = m
                                #print 'partial layer, m = ',m
                                #goto 123 #end l-loop
                                break
                        else:
                            #GJF: the following if statement is not in the fv_mapz, but it captures the case where pe2[kn] > pe1[km] where the m loop is not entered; without this, the lowest layer values are weird
                            if (l+1 == km):
                                dp = pe2[i,kn]-pe1[i,km]
                                esl = dp / dp1[i,km-1]
                                qsum = qsum + dp*(q4[1,i,km-1]+0.5*esl*(q4[2,i,km-1]-q4[1,i,km-1]+q4[3,i,km-1]*(1.-r23*esl)))
                            break
                        
                        break
                        #goto 123 #end l-loop
            if not next_k:
                q2[i,k] = qsum / dp2[i,k] #formerly labeled 123
                #print 'result q2 ', q2[i,k]
    #print q2
    #exit()
    return q2