import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

export interface PendingRequest {
    id: string;
    command: string;
    reason: string;
    status: string;
    timestamp: string;
}

export interface AuditLog {
    command: string;
    allowed: boolean;
    timestamp: string;
}

@Injectable({
    providedIn: 'root'
})
export class SentinelService {
    private apiUrl = ''; // Relative path for production serve

    constructor(private http: HttpClient) { }

    private getHeaders(): HttpHeaders {
        const token = localStorage.getItem('sentinel_token') || '';
        return new HttpHeaders({
            'Content-Type': 'application/json',
            'X-Sentinel-Token': token
        });
    }

    checkHealth(): Observable<boolean> {
        return this.http.get<{ status: string }>(`${this.apiUrl}/health`).pipe(
            map(res => res.status === 'healthy'),
            catchError(() => of(false))
        );
    }

    getPendingRequests(): Observable<PendingRequest[]> {
        return this.http.get<{ [key: string]: PendingRequest }>(`${this.apiUrl}/pending`, { headers: this.getHeaders() }).pipe(
            map(data => Object.values(data)),
            catchError(err => {
                console.error('Fetch pending failed', err);
                return of([]);
            })
        );
    }

    approveRequest(id: string): Observable<any> {
        return this.http.post(`${this.apiUrl}/approve/${id}`, {}, { headers: this.getHeaders() });
    }

    // Placeholder until backend supports it
    getAuditLogs(): Observable<AuditLog[]> {
        // Mock data for now
        return of([
            { command: 'ls -la', allowed: true, timestamp: 'Just now' },
            { command: 'rm -rf /', allowed: false, timestamp: '1m ago' }
        ]);
    }
}
